"""Service layer for quote creation, update, and approval."""
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

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
from app.services.part_pricing import (
    PRICE_SOURCE_UNPRICED,
    resolve_unit_price,
    resolve_unit_price_with_currency,
)

logger = logging.getLogger(__name__)

AUTO_CONFIRM_THRESHOLD = 80

# Phase-2 (spare-parts audit P2/P3): below this score the parts_matcher
# fallback must NOT auto-populate a line's ``spare_part_id``/price — the
# match is recorded as a suggestion only and the line is forced to review.
# 80 keeps exact (100) and prefix (85) matches but rejects fuzzy_code (75)
# and fuzzy_name (50) — exactly the "valve fuzzy-matched at 50%" defect.
LINE_ITEM_MATCH_THRESHOLD = 80.0

# The catalog resolver (the engine the auto-quote *gate* uses) is the
# source of truth for the line item's SKU. Only these two statuses are
# gate-approvable; the fuzzy ones are populated as review-only suggestions.
_GATE_OK_STATUSES = {"exact", "normalized"}
_RESOLVER_SUGGEST_STATUSES = {"fuzzy_prefix", "fuzzy_levenshtein"}

# Q5 — quantity bounds at line creation. Out-of-range values are kept
# (never silently coerced to 1) but flag the line as unconfirmed so a
# human reviews it.
MAX_LINE_QUANTITY = 100_000

# R5 — money is computed in Decimal then stored to the 2-dp NUMERIC
# columns as float, so cent-level float drift can't accumulate across a
# multi-line quote.
_CENTS = Decimal("0.01")


def _dec(value) -> Decimal:
    """Coerce any numeric/None to Decimal via str (avoids float artifacts)."""
    return Decimal(str(value if value is not None else 0))


def _money(amount: Decimal) -> float:
    """Quantize to 2 decimals (half-up) and return as float for storage."""
    return float(amount.quantize(_CENTS, rounding=ROUND_HALF_UP))


def _safe_quantity(raw) -> tuple[int, bool]:
    """Coerce a parsed quantity to a sane int. Returns ``(qty, suspect)``.

    ``suspect`` is True when the input was missing/unparseable/out-of-range
    so the caller can refuse to auto-confirm the line.
    """
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        return 1, True
    if qty < 1:
        return 1, True
    if qty > MAX_LINE_QUANTITY:
        return qty, True  # keep the value; flag for review
    return qty, False


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
            # Round-11 R11-AUTH-2 — verify customer belongs to caller's
            # tenant. Pre-fix, a rep could link quotes to other tenants'
            # customers by guessing the ID.
            await self._validate_customer(customer_id, tenant_id=tenant_id)

        # Round-15 Sprint 15k cohort 1 — Quote.tenant_id now NOT NULL.
        # If the caller didn't pass it, derive from created_by user.
        if tenant_id is None and created_by is not None:
            from app.models.user import User

            owner_row = await self._db.execute(
                select(User.tenant_id).where(User.id == created_by)
            )
            tenant_id = owner_row.scalar_one_or_none()

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

        # Round-15 Sprint 15k cohort 1 — Quote.tenant_id NOT NULL.
        # Inherit from the source email (which has tenant_id set via
        # the parsing pipeline).
        derived_tenant_id = getattr(email, "tenant_id", None)
        if derived_tenant_id is None and created_by is not None:
            from app.models.user import User

            owner_row = await self._db.execute(
                select(User.tenant_id).where(User.id == created_by)
            )
            derived_tenant_id = owner_row.scalar_one_or_none()

        quote_number = self.generate_quote_number()

        quote = Quote(
            tenant_id=derived_tenant_id,
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

    async def approve_quote(
        self,
        quote_id: int,
        approved_by: int,
        *,
        allow_unconfirmed: bool = False,
    ) -> Quote:
        """Approve a quote and generate PDF.

        T3 — the review flags produced upstream (``is_confirmed=False`` for
        fuzzy/quantity-uncertain/cross-currency matches, ``unit_price<=0``
        for unpriced lines) are *binding* here: a quote with any such line
        cannot be approved (and therefore cannot be sent) unless a manager
        explicitly overrides with ``allow_unconfirmed=True``, which the
        caller audit-logs. Without this gate every prior is_confirmed fix
        was advisory at the one step that reaches the customer.
        """
        quote = await self._get_quote_or_raise(quote_id)

        approvable_statuses = (QuoteStatus.DRAFT.value, QuoteStatus.PENDING_APPROVAL.value)
        self._require_status(quote, approvable_statuses, "onaylama")

        if not allow_unconfirmed:
            await self._assert_lines_confirmed_and_priced(quote_id)

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

    async def _assert_lines_confirmed_and_priced(self, quote_id: int) -> None:
        """T3 — raise unless every quote line is confirmed AND positively priced.

        ``is_confirmed=False`` marks a match the pipeline wasn't sure of
        (fuzzy SKU, quantity conflict/suspect, cross-currency); ``unit_price
        <= 0`` marks an unpriced line. Either must block approval/send.
        """
        items_result = await self._db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id)
        )
        items = list(items_result.scalars().all())
        if not items:
            raise BadRequestException(
                "Teklif onaylanamaz: satir bulunamadi."
            )
        unconfirmed = [it for it in items if not it.is_confirmed]
        unpriced = [it for it in items if (it.unit_price or 0) <= 0]
        if unconfirmed or unpriced:
            n_unconf = len(unconfirmed)
            n_unpriced = len(unpriced)
            raise BadRequestException(
                "Teklif onaylanamaz: "
                f"{n_unconf} satir dogrulanmamis, {n_unpriced} satir fiyatsiz. "
                "Once satirlari kontrol edip onaylayin "
                "(yonetici gerekirse zorla onaylayabilir)."
            )

    async def _recalculate_totals(self, quote: Quote) -> None:
        """Recalculate quote subtotal, discount_total, tax, and grand total in-place."""
        items_result = await self._db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        )
        items = items_result.scalars().all()

        # R5 — accumulate in Decimal so cents don't drift on large quotes.
        # subtotal = sum of discounted line totals
        subtotal = sum((_dec(item.line_total) for item in items), Decimal(0))

        # discount_total = sum of (gross - net) per line
        discount_total = sum(
            (
                (_dec(item.unit_price) * _dec(item.quantity)) - _dec(item.line_total)
                for item in items
            ),
            Decimal(0),
        )

        tax_amount = subtotal * (_dec(quote.tax_rate) / Decimal(100))
        grand_total = subtotal + tax_amount

        quote.subtotal = _money(subtotal)
        quote.discount_total = _money(discount_total)
        quote.tax_amount = _money(tax_amount)
        quote.grand_total = _money(grand_total)

        await self._db.flush()

    async def _create_quote_items(
        self, quote_id: int, items_data: list[dict]
    ) -> None:
        """Create QuoteItem records from a list of item dicts.

        This is the **manual** path (operator-authored create/update). Lines
        the operator typed with an explicit price are confirmed by
        definition — defaulting ``is_confirmed=True`` here so the T3 approval
        guard doesn't block a hand-entered quote. (The from-email path
        ``_create_items_with_matching`` sets ``is_confirmed`` from match
        confidence and is unaffected.)
        """
        for i, item_data in enumerate(items_data):
            spare_part_id = item_data.get("spare_part_id")
            quantity, _qty_suspect = _safe_quantity(item_data.get("quantity", 1))
            unit_price = float(item_data.get("unit_price", 0.0))
            discount_pct = float(item_data.get("discount_pct", 0.0))

            honeywell_code = item_data.get("honeywell_code")
            description = item_data.get("description")

            if spare_part_id and not honeywell_code:
                part = await self._find_spare_part_by_id(spare_part_id)
                if part:
                    honeywell_code = honeywell_code or part.honeywell_code
                    description = description or part.name_en

            discounted_price = _dec(unit_price) * (Decimal(1) - _dec(discount_pct) / Decimal(100))
            line_total = _dec(quantity) * discounted_price

            qi = QuoteItem(
                quote_id=quote_id,
                spare_part_id=spare_part_id,
                original_text=item_data.get("original_text"),
                honeywell_code=honeywell_code,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                discount_pct=discount_pct,
                line_total=_money(line_total),
                match_score=item_data.get("match_score"),
                match_strategy=item_data.get("match_strategy"),
                # Operator-authored lines default to confirmed (see docstring).
                is_confirmed=item_data.get("is_confirmed", True),
                sort_order=i,
            )
            self._db.add(qi)

        await self._db.flush()

    async def _create_items_with_matching(
        self, quote_id: int, parsed_data_json: str
    ) -> None:
        """Create quote items from parsed data with parts matching.

        Phase-2 unification (spare-parts audit P2/P3): the catalog resolver
        — the same engine the auto-quote gate trusts — is the source of
        truth for the line's SKU. ``parts_matcher`` is only a fallback for
        codes the resolver couldn't resolve, and even then its result is
        accepted only at/above :data:`LINE_ITEM_MATCH_THRESHOLD`; below
        that the SKU + price are left unset so the line is reviewed rather
        than silently bound to a low-confidence match.
        """
        try:
            parsed = json.loads(parsed_data_json)
        except json.JSONDecodeError:
            return

        parsed_parts = parsed.get("parts", []) or parsed.get("items", [])
        if not parsed_parts:
            return

        # T2 — collapse same-SKU duplicates before line creation. Parse-time
        # dedup already handles fresh emails; this also covers legacy
        # parsed_data stored before the dedup landed. Idempotent.
        from app.services.part_catalog_resolver import dedupe_parsed_parts

        parsed_parts = dedupe_parsed_parts(parsed_parts)

        preferred_currency = await self._quote_currency(quote_id)

        # Only run the (relatively expensive) matcher when at least one part
        # lacks a resolver verdict — i.e. the resolver returned unknown /
        # no_code, or this is legacy parsed_data from before the resolver.
        needs_matcher = any(
            not p.get("catalog_part_id") for p in parsed_parts
        )
        match_results = None
        if needs_matcher:
            try:
                from app.services.parts_matcher import match_parts

                match_results = await match_parts(self._db, parsed_parts)
            except Exception as exc:
                logger.warning(
                    "Parts matching failed, falling back to code lookup: %s", exc
                )
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
            quantity, qty_suspect = _safe_quantity(part_req.get("quantity", 1))
            # R1 — honor the upstream quantity-uncertainty flags
            # (extract_rows_as_parts / _merge_heuristic_parts). A body↔
            # attachment conflict leaves an in-range number that passes
            # _safe_quantity, so without this the line would be confirmed
            # despite the disagreement.
            if part_req.get("quantity_conflict") or part_req.get("quantity_suspect"):
                qty_suspect = True
            original_text = part_req.get("original_text", "")

            resolution = await self._resolve_line_match(
                part_req=part_req,
                code=code,
                match_result=(
                    match_results[i]
                    if match_results and i < len(match_results)
                    else None
                ),
                preferred_currency=preferred_currency,
            )

            if not description:
                description = resolution["description"]
            honeywell_code = resolution["honeywell_code"] or code

            # A line can only be auto-confirmed if the matcher confirmed it,
            # the quantity is sane, AND it carries a real price.
            is_confirmed = (
                resolution["is_confirmed"]
                and not qty_suspect
                and resolution["unit_price"] > 0
            )

            line_total = _dec(quantity) * _dec(resolution["unit_price"])

            qi = QuoteItem(
                quote_id=quote_id,
                spare_part_id=resolution["spare_part_id"],
                original_text=original_text,
                honeywell_code=honeywell_code,
                description=description,
                quantity=quantity,
                unit_price=resolution["unit_price"],
                line_total=_money(line_total),
                match_score=resolution["match_score"],
                match_strategy=resolution["match_strategy"],
                is_confirmed=is_confirmed,
                sort_order=i,
            )
            self._db.add(qi)

        await self._db.flush()

    async def _resolve_line_match(
        self,
        *,
        part_req: dict,
        code: str,
        match_result: dict | None,
        preferred_currency: str | None,
    ) -> dict:
        """Resolve one parsed part to a line-item SKU + price.

        Priority:
          1. Resolver gate verdict (exact/normalized) — auto-confirm + price.
          2. Resolver suggestion (fuzzy_prefix/levenshtein) — populate as a
             review-only suggestion (never auto-confirmed).
          3. parts_matcher top result, but only if score ≥ threshold.
          4. Direct exact-code lookup (legacy parsed_data without resolver).
        Anything else leaves ``spare_part_id`` unset (forced review).
        """
        out = {
            "spare_part_id": None,
            "honeywell_code": code,
            "description": "",
            "unit_price": 0.0,
            "match_score": None,
            "match_strategy": None,
            "is_confirmed": False,
        }

        catalog_part_id = part_req.get("catalog_part_id")
        catalog_status = part_req.get("catalog_status")

        # 1 + 2 — trust the resolver verdict (gate's own engine).
        if catalog_part_id and catalog_status in (
            _GATE_OK_STATUSES | _RESOLVER_SUGGEST_STATUSES
        ):
            part = await self._find_spare_part_by_id(catalog_part_id, active_only=True)
            if part:
                gate_ok = catalog_status in _GATE_OK_STATUSES
                await self._apply_part_to_resolution(
                    out, part, preferred_currency, code=code
                )
                out["match_strategy"] = f"catalog_{catalog_status}"
                out["match_score"] = 100.0 if catalog_status == "exact" else 96.0
                if not gate_ok:
                    out["match_score"] = 70.0  # suggestion strength
                out["is_confirmed"] = gate_ok and out["unit_price"] > 0
                return out

        # 3 — parts_matcher fallback, score-guarded.
        if match_result:
            matches = match_result.get("matches", [])
            if matches:
                best = matches[0]
                score = float(best.get("score", 0.0))
                # Always record the suggestion for the review UI.
                out["match_score"] = score
                out["match_strategy"] = best["strategy"]
                if score >= LINE_ITEM_MATCH_THRESHOLD:
                    part = await self._find_spare_part_by_id(
                        best["spare_part_id"], active_only=True
                    )
                    if part:
                        await self._apply_part_to_resolution(
                            out, part, preferred_currency, code=code
                        )
                        out["match_score"] = score
                        out["match_strategy"] = best["strategy"]
                        out["is_confirmed"] = (
                            score >= AUTO_CONFIRM_THRESHOLD and out["unit_price"] > 0
                        )
                return out

        # 4 — legacy direct exact-code lookup.
        if code:
            part = await self._find_spare_part_by_code(code, active_only=True)
            if part:
                await self._apply_part_to_resolution(
                    out, part, preferred_currency, code=code
                )
                out["match_score"] = 100.0
                out["match_strategy"] = "exact_code"
                out["is_confirmed"] = out["unit_price"] > 0

        return out

    async def _apply_part_to_resolution(
        self,
        out: dict,
        part: SparePart,
        preferred_currency: str | None,
        *,
        code: str,
    ) -> None:
        """Populate ``out`` with a part's SKU, canonical code, and sell price.

        R4 — the catalog price may be denominated in a different currency
        than the quote (the catalog commonly lists in USD, quotes default
        to TRY). We convert it into the quote currency via
        ``currency_service`` rather than silently writing a foreign-currency
        number onto the line. If conversion isn't possible (FX unavailable
        / unknown currency) the line is left unpriced for human review —
        never a wrong-currency number.
        """
        out["spare_part_id"] = part.id
        out["honeywell_code"] = part.honeywell_code or code
        unit_price, source, src_currency = resolve_unit_price_with_currency(
            part, preferred_currency=preferred_currency
        )

        if (
            unit_price > 0
            and src_currency
            and preferred_currency
            and src_currency.upper() != preferred_currency.upper()
        ):
            try:
                from app.services.currency_service import convert_currency

                unit_price = await convert_currency(
                    unit_price, src_currency, preferred_currency
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Part %s price is in %s but quote is %s and FX conversion "
                    "failed (%s) — leaving the line unpriced for review.",
                    part.id,
                    src_currency,
                    preferred_currency,
                    exc,
                )
                unit_price = 0.0
                source = PRICE_SOURCE_UNPRICED

        out["unit_price"] = unit_price
        if source == PRICE_SOURCE_UNPRICED or unit_price <= 0:
            logger.info(
                "Part %s (%s) resolved but has no safe sell price — line left "
                "unpriced for review.",
                part.id,
                part.honeywell_code,
            )
        if not out["description"]:
            out["description"] = part.name_en or part.name_tr or ""

    async def _quote_currency(self, quote_id: int) -> str | None:
        """Best-effort fetch of the quote's currency for price selection."""
        result = await self._db.execute(
            select(Quote.currency).where(Quote.id == quote_id)
        )
        return result.scalar_one_or_none()

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
            quantity, _qty_suspect = _safe_quantity(item.get("quantity", 1))

            spare_part_id = None
            unit_price = 0.0
            if code:
                part = await self._find_spare_part_by_code(code, active_only=True)
                if part:
                    spare_part_id = part.id
                    unit_price, _src = resolve_unit_price(part)

            line_total = _money(_dec(quantity) * _dec(unit_price))

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

    async def _validate_customer(
        self, customer_id: int, tenant_id: int | None = None
    ) -> Customer:
        """Raise NotFoundException if customer does not exist or belongs to another tenant.

        Round-11 R11-AUTH-2 — cross-tenant access maps to 404 (not 403)
        to avoid leaking the existence of foreign-tenant customer rows.
        """
        customer = await self._get_or_raise(Customer, customer_id, "Customer")
        if tenant_id is not None:
            cust_tenant = getattr(customer, "tenant_id", None)
            # NULL tenant rows are legacy single-tenant data — allow them
            # so existing deployments don't break. Mismatched non-NULL
            # tenant is a cross-tenant probe.
            if cust_tenant is not None and cust_tenant != tenant_id:
                raise NotFoundException(
                    f"{customer_id} numarali Customer bulunamadi"
                )
        return customer

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

    async def _find_spare_part_by_id(
        self, part_id: int, *, active_only: bool = False
    ) -> SparePart | None:
        # T1 — ``active_only`` guards the from-email path: a stale
        # ``catalog_part_id`` (resolved when the part was active, quoted
        # later after it was discontinued) must not silently price an
        # inactive part. The manual quote path leaves it False so an
        # operator can still quote a part being phased out.
        stmt = select(SparePart).where(SparePart.id == part_id)
        if active_only:
            stmt = stmt.where(SparePart.is_active.is_(True))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_spare_part_by_code(
        self, code: str, *, active_only: bool = False
    ) -> SparePart | None:
        stmt = select(SparePart).where(SparePart.honeywell_code == code)
        if active_only:
            stmt = stmt.where(SparePart.is_active.is_(True))
        result = await self._db.execute(stmt)
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
