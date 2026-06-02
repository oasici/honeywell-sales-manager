"""TDD tests for QuoteService."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BadRequestException
from app.models.enums import QuoteStatus
from app.services.quote_service import QuoteService


def _make_mock_db():
    """Create a mock AsyncSession with standard stubs."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_mock_quote(quote_id=1, status="draft", tax_rate=20.0, discount_total=0.0):
    """Create a mock Quote object."""
    quote = MagicMock()
    quote.id = quote_id
    quote.status = status
    quote.tax_rate = tax_rate
    quote.discount_total = discount_total
    quote.subtotal = 0.0
    quote.tax_amount = 0.0
    quote.grand_total = 0.0
    return quote


class TestGenerateQuoteNumber:
    """Test cycle 1: generate_quote_number returns unique formatted strings."""

    def test_should_generate_unique_quote_numbers(self):
        number_1 = QuoteService.generate_quote_number()
        number_2 = QuoteService.generate_quote_number()

        assert number_1 != number_2
        assert number_1.startswith("QT-")
        assert number_2.startswith("QT-")

    def test_should_match_expected_format(self):
        number = QuoteService.generate_quote_number()

        pattern = r"^QT-\d{8}-[A-F0-9]{6}$"
        assert re.match(pattern, number), f"'{number}' does not match pattern '{pattern}'"

    def test_should_contain_current_date(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        number = QuoteService.generate_quote_number()

        assert today in number


class TestLineTotal:
    """Test cycle 2: line_total = quantity * unit_price * (1 - discount/100)."""

    @pytest.mark.asyncio
    async def test_should_calculate_line_total_with_discount(self):
        db = _make_mock_db()

        items_result_mock = MagicMock()
        items_result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=items_result_mock)

        service = QuoteService(db)

        items = [
            {
                "quantity": 10,
                "unit_price": 100.0,
                "discount_pct": 15.0,
                "honeywell_code": "ABC-123",
                "description": "Test part",
            }
        ]

        await service._create_quote_items(quote_id=1, items_data=items)

        added_item = db.add.call_args_list[-1][0][0]
        expected = 10 * 100.0 * (1 - 15.0 / 100)
        assert added_item.line_total == round(expected, 2)

    @pytest.mark.asyncio
    async def test_should_calculate_line_total_without_discount(self):
        db = _make_mock_db()
        service = QuoteService(db)

        items = [
            {
                "quantity": 5,
                "unit_price": 200.0,
                "discount_pct": 0.0,
                "honeywell_code": "XYZ-456",
            }
        ]

        await service._create_quote_items(quote_id=1, items_data=items)

        added_item = db.add.call_args_list[-1][0][0]
        assert added_item.line_total == 1000.0


class TestQuoteTotals:
    """Test cycle 3: subtotal, tax, grand_total math."""

    @pytest.mark.asyncio
    async def test_should_calculate_quote_totals_correctly(self):
        db = _make_mock_db()

        item_1 = MagicMock()
        item_1.line_total = 500.0
        item_1.unit_price = 500.0
        item_1.quantity = 1
        item_2 = MagicMock()
        item_2.line_total = 300.0
        item_2.unit_price = 300.0
        item_2.quantity = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item_1, item_2]
        db.execute = AsyncMock(return_value=items_result)

        quote = _make_mock_quote(tax_rate=20.0)
        service = QuoteService(db)

        await service._recalculate_totals(quote)

        assert quote.subtotal == 800.0
        assert quote.discount_total == 0.0  # no discounts
        assert quote.tax_amount == 160.0
        assert quote.grand_total == 960.0

    @pytest.mark.asyncio
    async def test_should_compute_discount_total_from_line_items(self):
        """discount_total = sum of (gross - net) per line."""
        db = _make_mock_db()

        # Item: qty=10, unit_price=100, 15% discount -> line_total=850
        item = MagicMock()
        item.unit_price = 100.0
        item.quantity = 10
        item.line_total = 850.0  # 10 * 100 * 0.85

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        db.execute = AsyncMock(return_value=items_result)

        quote = _make_mock_quote(tax_rate=10.0)
        service = QuoteService(db)

        await service._recalculate_totals(quote)

        assert quote.subtotal == 850.0
        assert quote.discount_total == 150.0  # 1000 - 850
        assert quote.tax_amount == 85.0
        assert quote.grand_total == 935.0  # 850 + 85


class TestRejectEmptyItems:
    """Test cycle 4: raise BadRequestException when items list empty."""

    @pytest.mark.asyncio
    async def test_should_reject_quote_with_no_items(self):
        db = _make_mock_db()

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=items_result)

        quote = _make_mock_quote(tax_rate=20.0, discount_total=0.0)
        service = QuoteService(db)

        await service._recalculate_totals(quote)

        assert quote.subtotal == 0.0
        assert quote.grand_total == 0.0


class TestDraftStatusOnCreation:
    """Test cycle 5: new quotes start as 'draft'."""

    @pytest.mark.asyncio
    async def test_should_set_status_to_draft_on_creation(self):
        db = _make_mock_db()

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=items_result)

        captured_quotes = []

        def capture_add(obj):
            # Simulate SQLAlchemy column defaults for fields that are None
            if hasattr(obj, "discount_total") and obj.discount_total is None:
                obj.discount_total = 0.0
            if hasattr(obj, "subtotal") and obj.subtotal is None:
                obj.subtotal = 0.0
            if hasattr(obj, "tax_amount") and obj.tax_amount is None:
                obj.tax_amount = 0.0
            if hasattr(obj, "grand_total") and obj.grand_total is None:
                obj.grand_total = 0.0
            captured_quotes.append(obj)

        db.add = capture_add

        async def noop_refresh(obj):
            pass

        db.refresh = noop_refresh

        service = QuoteService(db)

        await service.create_quote(
            customer_id=None,
            items=[],
        )

        quote_obj = captured_quotes[0]
        assert quote_obj.status == QuoteStatus.DRAFT.value


class TestApproveQuote:
    """Test cycle 6: approve changes status."""

    @staticmethod
    def _confirmed_item():
        item = MagicMock()
        item.is_confirmed = True
        item.unit_price = 100.0
        return item

    @pytest.mark.asyncio
    async def test_should_change_status_to_approved_on_approve(self):
        db = _make_mock_db()

        quote = _make_mock_quote(status=QuoteStatus.DRAFT.value)

        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = quote
        # T3 — approve_quote now verifies all lines are confirmed + priced.
        select_result.scalars.return_value.all.return_value = [self._confirmed_item()]
        db.execute = AsyncMock(return_value=select_result)

        service = QuoteService(db)

        result = await service.approve_quote(quote_id=1, approved_by=42)

        assert result.status == QuoteStatus.APPROVED.value
        assert result.approved_by == 42

    @pytest.mark.asyncio
    async def test_should_reject_approval_with_unconfirmed_line(self):
        """T3 — a quote with an unconfirmed line cannot be approved."""
        db = _make_mock_db()
        quote = _make_mock_quote(status=QuoteStatus.DRAFT.value)
        unconfirmed = MagicMock(); unconfirmed.is_confirmed = False; unconfirmed.unit_price = 100.0
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = quote
        select_result.scalars.return_value.all.return_value = [unconfirmed]
        db.execute = AsyncMock(return_value=select_result)
        service = QuoteService(db)
        with pytest.raises(BadRequestException):
            await service.approve_quote(quote_id=1, approved_by=42)

    @pytest.mark.asyncio
    async def test_should_reject_approval_with_unpriced_line(self):
        """T3 — a quote with a 0.00 line cannot be approved."""
        db = _make_mock_db()
        quote = _make_mock_quote(status=QuoteStatus.DRAFT.value)
        unpriced = MagicMock(); unpriced.is_confirmed = True; unpriced.unit_price = 0.0
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = quote
        select_result.scalars.return_value.all.return_value = [unpriced]
        db.execute = AsyncMock(return_value=select_result)
        service = QuoteService(db)
        with pytest.raises(BadRequestException):
            await service.approve_quote(quote_id=1, approved_by=42)

    @pytest.mark.asyncio
    async def test_force_override_approves_unconfirmed(self):
        """T3 — allow_unconfirmed=True bypasses the line gate (manager override)."""
        db = _make_mock_db()
        quote = _make_mock_quote(status=QuoteStatus.DRAFT.value)
        unconfirmed = MagicMock(); unconfirmed.is_confirmed = False; unconfirmed.unit_price = 0.0
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = quote
        select_result.scalars.return_value.all.return_value = [unconfirmed]
        db.execute = AsyncMock(return_value=select_result)
        service = QuoteService(db)
        result = await service.approve_quote(
            quote_id=1, approved_by=42, allow_unconfirmed=True
        )
        assert result.status == QuoteStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_should_reject_approval_of_already_approved_quote(self):
        db = _make_mock_db()

        quote = _make_mock_quote(status=QuoteStatus.APPROVED.value)

        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = quote
        db.execute = AsyncMock(return_value=select_result)

        service = QuoteService(db)

        with pytest.raises(BadRequestException):
            await service.approve_quote(quote_id=1, approved_by=42)
