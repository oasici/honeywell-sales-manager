"""Service layer for quote creation, update, and approval."""
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import EmailStatus, QuoteStatus
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart
from app.models.user import User
from app.services.opportunity_linking_service import ensure_opportunity_for_email

logger = logging.getLogger(__name__)

AUTO_CONFIRM_THRESHOLD = 80


class QuoteService:
    """Encapsulates all quote business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_quote(
        self,
        customer_id: int | None,
        items: list[dict],
        language: str = "tr",
        currency: str = "TRY",
        tax_rate: float = 20.0,
        notes: str | None = None,
        created_by: int | None = None,
        valid_days: int = 30,
        tenant_id: int | None = None,
    ) -> Quote:
        """Create a new quote with optional line items."""
        if customer_id:
            await self._validate_customer(customer_id)

        quote_number = self.generate_quote_number()

        quote = Quote(
            quote_number=quote_number,
            customer_id=customer_id,
            created_by=created_by,
            status=QuoteStatus.DRAFT.value,
            language=language,
            currency=currency,
            tax_rate=tax_rate,
            valid_days=valid_days,
            notes=notes,
            # V12 multi-tenant: caller passes the requesting user's tenant.
            tenant_id=tenant_id,
        )
        self._db.add(quote)
        await self._db.flush()

        await self._create_quote_items(quote.id, items)
        await self._recalculate_totals(quote)
        await self._db.refresh(quote)

        return quote

    async def create_quote_from_email(
        self,
        email_id: int,
        created_by: int | None = None,
    ) -> Quote:
        """Create a quote from a parsed email request with auto-matching."""
        email = await self._get_email_or_raise(email_id)

        if email.status == EmailStatus.NEW.value:
            raise BadRequestException("E-posta henuz ayristirilmadi")

        if not email.customer_id:
            raise BadRequestException("E-posta musteriyle eslesmemis (customer_id yok)")

        # v2 consistency: ensure email ↔ opportunity is set, then quote links to same opportunity
        opportunity_id = email.opportunity_id or await ensure_opportunity_for_email(
            self._db,
            email=email,
            owner_hint=created_by or email.assigned_to,
        )
        email.opportunity_id = opportunity_id

        quote_number = self.generate_quote_number()

        quote = Quote(
            quote_number=quote_number,
            customer_id=email.customer_id,
            email_request_id=email.id,
            created_by=created_by,
            status=QuoteStatus.DRAFT.value,
            language=email.language or "tr",
            opportunity_id=opportunity_id,
        )
        self._db.add(quote)
        await self._db.flush()

        if email.parsed_data:
            await self._create_items_with_matching(quote.id, email.parsed_data)

        email.status = EmailStatus.QUOTED.value
        await self._db.flush()

        await self._recalculate_totals(quote)
        await self._db.refresh(quote)

        return quote

    async def update_quote(self, quote_id: int, data: dict, items: list[dict] | None = None) -> Quote:
        """Update quote header fields and optionally replace items."""
        quote = await self._get_quote_or_raise(quote_id)

        editable_statuses = (QuoteStatus.DRAFT.value, QuoteStatus.PENDING_APPROVAL.value)
        self._require_status(quote, editable_statuses, "duzenleme")

        header_fields = [
            "customer_id",
            "language",
            "currency",
            "tax_rate",
            "valid_days",
            "notes",
        ]
        for field in header_fields:
            if field in data:
                setattr(quote, field, data[field])

        if items is not None:
            await self._replace_items(quote_id, items)

        await self._recalculate_totals(quote)
        await self._db.refresh(quote)

        return quote

    async def approve_quote(self, quote_id: int, approved_by: int) -> Quote:
        """Approve a quote and generate PDF."""
        quote = await self._get_quote_or_raise(quote_id)

        approvable_statuses = (QuoteStatus.DRAFT.value, QuoteStatus.PENDING_APPROVAL.value)
        self._require_status(quote, approvable_statuses, "onaylama")

        quote.approved_by = approved_by

        # Generate PDF before marking as approved
        try:
            from app.services.quote_generator import generate_quote_pdf

            quote_data = await self._build_quote_data(quote, approved_by)
            pdf_path = await generate_quote_pdf(quote_data, quote.language)
            quote.pdf_path = pdf_path
            logger.info(
                "Generated PDF for quote %s: %s",
                quote.quote_number,
                pdf_path,
            )
        except Exception as exc:
            logger.error(
                "Failed to generate PDF for quote %s: %s",
                quote.quote_number,
                exc,
            )
            raise BadRequestException(
                f"PDF olusturma basarisiz oldu: {exc}"
            )

        quote.status = QuoteStatus.APPROVED.value

        await self._db.flush()
        await self._db.refresh(quote)

        return quote

    @staticmethod
    def generate_quote_number() -> str:
        """Generate a unique quote number."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        short_id = uuid.uuid4().hex[:6].upper()
        return f"QT-{timestamp}-{short_id}"

    @staticmethod
    def _require_status(quote: Quote, allowed: tuple[str, ...], action: str) -> None:
        """Raise BadRequestException if quote is not in an allowed status."""
        if quote.status not in allowed:
            allowed_labels = ", ".join(allowed)
            raise BadRequestException(
                f"'{quote.status}' durumundaki teklif icin '{action}' islemi yapilamaz. "
                f"Izin verilen durumlar: {allowed_labels}"
            )

    # ---- Private helpers ----

    async def _recalculate_totals(self, quote: Quote) -> None:
        """Recalculate quote subtotal, discount_total, tax, and grand total in-place."""
        items_result = await self._db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        )
        items = items_result.scalars().all()

        # subtotal = sum of discounted line totals
        subtotal = sum(item.line_total for item in items)

        # discount_total = sum of (gross - net) per line
        discount_total = sum(
            (item.unit_price * item.quantity) - item.line_total
            for item in items
        )

        tax_amount = subtotal * (quote.tax_rate / 100)
        grand_total = subtotal + tax_amount

        quote.subtotal = round(subtotal, 2)
        quote.discount_total = round(discount_total, 2)
        quote.tax_amount = round(tax_amount, 2)
        quote.grand_total = round(grand_total, 2)

        await self._db.flush()

    async def _create_quote_items(
        self, quote_id: int, items_data: list[dict]
    ) -> None:
        """Create QuoteItem records from a list of item dicts."""
        for i, item_data in enumerate(items_data):
            spare_part_id = item_data.get("spare_part_id")
            quantity = int(item_data.get("quantity", 1))
            unit_price = float(item_data.get("unit_price", 0.0))
            discount_pct = float(item_data.get("discount_pct", 0.0))

            honeywell_code = item_data.get("honeywell_code")
            description = item_data.get("description")

            if spare_part_id and not honeywell_code:
                part = await self._find_spare_part_by_id(spare_part_id)
                if part:
                    honeywell_code = honeywell_code or part.honeywell_code
                    description = description or part.name_en

            discounted_price = unit_price * (1 - discount_pct / 100)
            line_total = quantity * discounted_price

            qi = QuoteItem(
                quote_id=quote_id,
                spare_part_id=spare_part_id,
                original_text=item_data.get("original_text"),
                honeywell_code=honeywell_code,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                discount_pct=discount_pct,
                line_total=round(line_total, 2),
                match_score=item_data.get("match_score"),
                match_strategy=item_data.get("match_strategy"),
                is_confirmed=item_data.get("is_confirmed", False),
                sort_order=i,
            )
            self._db.add(qi)

        await self._db.flush()

    async def _create_items_with_matching(
        self, quote_id: int, parsed_data_json: str
    ) -> None:
        """Create quote items from parsed data with parts matching."""
        try:
            parsed = json.loads(parsed_data_json)
        except json.JSONDecodeError:
            return

        parsed_parts = parsed.get("parts", []) or parsed.get("items", [])
        if not parsed_parts:
            return

        # Run parts matcher for best catalog matches
        try:
            from app.services.parts_matcher import match_parts

            match_results = await match_parts(self._db, parsed_parts)
        except Exception as exc:
            logger.warning("Parts matching failed, falling back to code lookup: %s", exc)
            match_results = None

        for i, part_req in enumerate(parsed_parts):
            code = (
                part_req.get("part_code")
                or part_req.get("honeywell_code")
                or part_req.get("code", "")
            )
            description = (
                part_req.get("part_description")
                or part_req.get("description", "")
            )
            quantity = int(part_req.get("quantity", 1))
            original_text = part_req.get("original_text", "")

            spare_part_id = None
            unit_price = 0.0
            match_score = None
            match_strategy = None
            is_confirmed = False
            honeywell_code = code

            # Use match results if available
            if match_results and i < len(match_results):
                matches = match_results[i].get("matches", [])
                if matches:
                    best = matches[0]
                    spare_part_id = best["spare_part_id"]
                    honeywell_code = best.get("honeywell_code", code)
                    match_score = best["score"]
                    match_strategy = best["strategy"]
                    is_confirmed = match_score >= AUTO_CONFIRM_THRESHOLD

                    # Look up price from spare part
                    part = await self._find_spare_part_by_id(spare_part_id)
                    if part:
                        if part.transfer_price:
                            unit_price = part.transfer_price
                        elif part.supplier_price:
                            unit_price = part.supplier_price
                        elif part.prices:
                            unit_price = part.prices[0].net_price
                        if not description:
                            description = part.name_en or part.name_tr or ""
            else:
                # Fallback: direct code lookup
                if code:
                    part = await self._find_spare_part_by_code(code)
                    if part:
                        spare_part_id = part.id
                        honeywell_code = part.honeywell_code
                        match_score = 100.0
                        match_strategy = "exact_code"
                        is_confirmed = True
                        if part.transfer_price:
                            unit_price = part.transfer_price
                        elif part.supplier_price:
                            unit_price = part.supplier_price
                        elif part.prices:
                            unit_price = part.prices[0].net_price

            line_total = quantity * unit_price

            qi = QuoteItem(
                quote_id=quote_id,
                spare_part_id=spare_part_id,
                original_text=original_text,
                honeywell_code=honeywell_code,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                line_total=round(line_total, 2),
                match_score=match_score,
                match_strategy=match_strategy,
                is_confirmed=is_confirmed,
                sort_order=i,
            )
            self._db.add(qi)

        await self._db.flush()

    async def _create_items_from_parsed_data(
        self, quote_id: int, parsed_data_json: str
    ) -> None:
        """Create quote items from email parsed_data JSON (legacy fallback)."""
        try:
            parsed = json.loads(parsed_data_json)
        except json.JSONDecodeError:
            return

        items = parsed.get("items", [])
        for i, item in enumerate(items):
            code = item.get("honeywell_code") or item.get("code", "")
            quantity = int(item.get("quantity", 1))

            spare_part_id = None
            unit_price = 0.0
            if code:
                part = await self._find_spare_part_by_code(code)
                if part:
                    spare_part_id = part.id
                    if part.prices:
                        unit_price = part.prices[0].net_price

            line_total = quantity * unit_price

            qi = QuoteItem(
                quote_id=quote_id,
                spare_part_id=spare_part_id,
                original_text=item.get("original_text", ""),
                honeywell_code=code,
                description=item.get("description", ""),
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
                match_score=item.get("match_score"),
                match_strategy=item.get("match_strategy"),
                sort_order=i,
            )
            self._db.add(qi)

        await self._db.flush()

    async def _replace_items(
        self, quote_id: int, items_data: list[dict]
    ) -> None:
        """Delete existing items and create new ones."""
        existing_result = await self._db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id)
        )
        for item in existing_result.scalars().all():
            await self._db.delete(item)
        await self._db.flush()

        await self._create_quote_items(quote_id, items_data)

    async def _validate_customer(self, customer_id: int) -> Customer:
        """Raise NotFoundException if customer does not exist."""
        return await self._get_or_raise(Customer, customer_id, "Customer")

    async def _get_quote_or_raise(self, quote_id: int) -> Quote:
        return await self._get_or_raise(Quote, quote_id, "Quote")

    async def _get_email_or_raise(self, email_id: int) -> EmailRequest:
        return await self._get_or_raise(EmailRequest, email_id, "Email")

    async def _get_or_raise(self, model: type, record_id: int, label: str):
        """Generic fetch-by-id with NotFoundException."""
        result = await self._db.execute(select(model).where(model.id == record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise NotFoundException(f"{record_id} numarali {label} bulunamadi")
        return record

    async def _find_spare_part_by_id(self, part_id: int) -> SparePart | None:
        result = await self._db.execute(select(SparePart).where(SparePart.id == part_id))
        return result.scalar_one_or_none()

    async def _find_spare_part_by_code(self, code: str) -> SparePart | None:
        result = await self._db.execute(select(SparePart).where(SparePart.honeywell_code == code))
        return result.scalar_one_or_none()

    async def _build_quote_data(self, quote: Quote, user_id: int | None = None) -> dict:
        """Build the data dict needed by generate_quote_pdf."""
        from app.core.config import settings

        # Fetch items
        items_result = await self._db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        )
        items = items_result.scalars().all()

        items_data = [
            {
                "honeywell_code": item.honeywell_code or "",
                "description": item.description or "",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount_pct": item.discount_pct,
                "line_total": item.line_total,
            }
            for item in items
        ]

        # Customer info
        customer_name = ""
        customer_company = ""
        customer_address = ""
        customer_phone = ""
        customer_email = ""
        customer_tax_id = ""
        if quote.customer:
            customer_name = quote.customer.name or ""
            customer_company = quote.customer.company or ""
            customer_address = quote.customer.address or ""
            customer_phone = quote.customer.phone or ""
            customer_email = quote.customer.email or ""
            customer_tax_id = quote.customer.tax_id or ""

        # Prepared-by info
        prepared_by_name = ""
        prepared_by_email = ""
        if user_id:
            user_result = await self._db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                prepared_by_name = user.full_name
                prepared_by_email = user.email

        created_date = ""
        if quote.created_at:
            created_date = quote.created_at.strftime("%Y-%m-%d")

        return {
            "quote_number": quote.quote_number,
            "created_date": created_date,
            "valid_days": quote.valid_days,
            "currency": quote.currency,
            "customer_name": customer_name,
            "customer_company": customer_company,
            "customer_address": customer_address,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "customer_tax_id": customer_tax_id,
            "prepared_by_name": prepared_by_name,
            "prepared_by_email": prepared_by_email,
            "prepared_by_department": "Sales Department",
            "items": items_data,
            "subtotal": quote.subtotal,
            "discount_total": quote.discount_total,
            "tax_rate": quote.tax_rate,
            "tax_amount": quote.tax_amount,
            "grand_total": quote.grand_total,
            "notes": quote.notes or "",
        }
