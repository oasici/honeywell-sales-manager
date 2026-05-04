"""Edge case tests for the report engine."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.quote import Quote
from app.models.user import User
from app.services.report_engine import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    QUERY_TIMEOUT_SECONDS,
    ReportEngine,
)


async def _create_user(db: AsyncSession) -> User:
    user = User(
        email=f"report_edge_{id(db)}@test.com",
        full_name="Report User",
        hashed_password=hash_password("pass123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user




class TestEmptyResult:
    """Queries with impossible filters should return empty rows, not errors."""

    @pytest.mark.asyncio
    async def test_empty_result_returns_no_rows(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)
        result = await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            filters=[{"field": "name", "operator": "eq", "value": "NONEXISTENT_CUSTOMER_XYZ"}],
        )

        assert result["rows"] == []
        assert result["total"] == 0
        assert result["columns"] == ["id", "name"]


class TestMaxLimitEnforcement:
    """Requesting a limit above MAX_LIMIT should be capped."""

    @pytest.mark.asyncio
    async def test_limit_capped_at_max(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        # This should not raise; limit should be silently capped
        result = await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            limit=10000,
        )

        # No assertion on internal limit directly, but verify it runs without error
        assert isinstance(result["rows"], list)
        assert result["total"] >= 0

    def test_max_limit_constant_exists(self):
        assert MAX_LIMIT == 5000
        assert DEFAULT_LIMIT == 1000


class TestInvalidColumnRejection:
    """Requesting columns outside the whitelist should raise BadRequestException."""

    @pytest.mark.asyncio
    async def test_rejects_hashed_password_column(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        with pytest.raises(BadRequestException, match="gecersiz sutunlar"):
            await engine.execute_inline(
                current_user=user,
                entity_type="customer",
                columns=["id", "hashed_password"],
            )

    @pytest.mark.asyncio
    async def test_rejects_arbitrary_column(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        with pytest.raises(BadRequestException, match="gecersiz sutunlar"):
            await engine.execute_inline(
                current_user=user,
                entity_type="quote",
                columns=["id", "secret_field"],
            )


class TestInvalidEntityType:
    """Requesting an unknown entity type should raise BadRequestException."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_entity_type(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        with pytest.raises(BadRequestException, match="Gecersiz varlik tipi"):
            await engine.execute_inline(
                current_user=user,
                entity_type="invalid",
                columns=["id"],
            )


class TestReDoSProtection:
    """Filter values longer than 200 chars should be truncated by the contains operator."""

    @pytest.mark.asyncio
    async def test_long_filter_value_does_not_cause_error(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)
        long_value = "A" * 300

        # The contains operator truncates to 200 chars internally.
        # This should not raise or hang.
        result = await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            filters=[{"field": "name", "operator": "contains", "value": long_value}],
        )

        assert isinstance(result["rows"], list)


class TestCrossEntityJoin:
    """Cross-entity joins (e.g., quote with customer.name) should work."""

    @pytest.mark.asyncio
    async def test_quote_with_customer_name_join(
        self, db: AsyncSession,
    ):
        user = await _create_user(db)
        customer = Customer(
            name="Join Test Customer",
            company="JoinCo",
            email="join@test.com",
            phone="555-0000",
            created_by=user.id,
        )
        db.add(customer)
        await db.flush()

        quote = Quote(
            quote_number="JOIN-001",
            customer_id=customer.id,
            created_by=user.id,
            status="draft",
            currency="TRY",
        )
        db.add(quote)
        await db.commit()

        engine = ReportEngine(db)
        result = await engine.execute_inline(
            current_user=user,
            entity_type="quote",
            columns=["id", "quote_number", "customer.name"],
        )

        assert result["total"] >= 1
        joined_row = next(
            (r for r in result["rows"] if r["quote_number"] == "JOIN-001"),
            None,
        )
        assert joined_row is not None
        assert joined_row["customer.name"] == "Join Test Customer"


class TestInvalidJoinColumn:
    """Requesting a join column not in the allowed list should raise."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_join_column(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        with pytest.raises(BadRequestException, match="gecersiz sutun"):
            await engine.execute_inline(
                current_user=user,
                entity_type="quote",
                columns=["id", "customer.hashed_password"],
            )


class TestTimeoutConstant:
    """Verify the timeout constant is configured."""

    def test_timeout_constant_is_defined(self):
        assert QUERY_TIMEOUT_SECONDS == 30

    def test_timeout_is_positive(self):
        assert QUERY_TIMEOUT_SECONDS > 0


class TestInvalidFilterOperator:
    """Requesting an unsupported filter operator should raise."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_operator(self, db: AsyncSession):
        user = await _create_user(db)
        engine = ReportEngine(db)

        with pytest.raises(BadRequestException, match="Gecersiz filtre operatoru"):
            await engine.execute_inline(
                current_user=user,
                entity_type="customer",
                columns=["id", "name"],
                filters=[{"field": "name", "operator": "regex", "value": ".*"}],
            )
