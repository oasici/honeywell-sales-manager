"""Dynamic report execution engine using SQLAlchemy query builder."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.report import ReportTemplate
from app.models.user import User
from app.services.tenant_context import (
    assert_same_tenant,
    scoped_for_user,
)

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SECONDS = 30

# Model registry: entity_type -> (model_class, allowed_columns)
# SECURITY: Column whitelist prevents exposure of sensitive fields
ENTITY_MODEL_MAP: dict[str, tuple[type, list[str]]] = {
    "quote": (
        Quote,
        [
            "id",
            "quote_number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "tax_amount",
            "grand_total",
            "valid_days",
            "created_at",
        ],
    ),
    "opportunity": (
        Opportunity,
        [
            "id",
            "title",
            "stage",
            "amount",
            "currency",
            "close_date",
            "status",
            "forecast_category",
            "created_at",
        ],
    ),
    "customer": (
        Customer,
        [
            "id",
            "name",
            "company",
            "email",
            "phone",
            "created_at",
        ],
    ),
    "email": (
        EmailRequest,
        [
            "id",
            "from_address",
            "subject",
            "status",
            "category",
            "category_confidence",
            "sentiment",
            "created_at",
        ],
    ),
}

ALLOWED_COLUMNS: dict[str, list[str]] = {
    entity: cols for entity, (_, cols) in ENTITY_MODEL_MAP.items()
}

FILTER_OPERATORS = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "contains": lambda col, val: col.ilike(f"%{str(val)[:200]}%"),
    "is_null": lambda col, val: col.is_(None) if val else col.isnot(None),
}

DEFAULT_LIMIT = 1000
MAX_LIMIT = 5000
# D-035 — buffered paths cap at MAX_LIMIT (5K). The streaming export
# path doesn't hold rows in memory, so it can serve far larger result
# sets; this is a runaway-safety ceiling, not a memory constraint.
MAX_STREAM_ROWS = 200_000

# Cross-entity join definitions: base_entity -> joinable_entity -> join config
ENTITY_JOINS: dict[str, dict[str, dict]] = {
    "quote": {
        "customer": {
            "fk": "customer_id",
            "model": Customer,
            "columns": ["name", "company", "email"],
        },
        "opportunity": {
            "fk": "opportunity_id",
            "model": Opportunity,
            "columns": ["title", "stage", "amount"],
        },
    },
    "opportunity": {
        "customer": {
            "fk": "customer_id",
            "model": Customer,
            "columns": ["name", "company", "email"],
        },
        "owner": {
            "fk": "owner_id",
            "model": User,
            "columns": ["full_name", "email"],
        },
    },
    "email": {
        "customer": {
            "fk": "customer_id",
            "model": Customer,
            "columns": ["name", "company"],
        },
        "opportunity": {
            "fk": "opportunity_id",
            "model": Opportunity,
            "columns": ["title", "stage"],
        },
    },
}

# Columns that support numeric aggregation (sum, avg)
NUMERIC_COLUMNS: set[str] = {
    "subtotal",
    "discount_total",
    "tax_amount",
    "grand_total",
    "valid_days",
    "amount",
    "category_confidence",
}


class ReportEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_report(
        self,
        template_id: int,
        current_user,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict:
        """Execute report from saved template.

        Round-4 R4-TEN-14 — ``current_user`` is now mandatory. The
        template lookup is tenant-scoped, and ``execute_inline``
        injects a ``WHERE model.tenant_id = current_user.tenant_id``
        predicate on every entity_type the engine knows about.
        """
        stmt = select(ReportTemplate).where(ReportTemplate.id == template_id)
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundException("Rapor sablonu bulunamadi")
        # Cross-tenant template loads map to 404 so a manager can't
        # execute a foreign-tenant template at all.
        assert_same_tenant(
            template, current_user, exception_cls=NotFoundException
        )

        columns = json.loads(template.columns_json)
        filters = json.loads(template.filters_json) if template.filters_json else None

        return await self.execute_inline(
            entity_type=template.entity_type,
            columns=columns,
            current_user=current_user,
            filters=filters,
            group_by=template.group_by,
            sort_by=template.sort_by,
            sort_order=template.sort_order,
            limit=limit,
            offset=offset,
        )

    async def execute_inline(
        self,
        entity_type: str,
        columns: list[str],
        current_user,
        filters: list[dict] | None = None,
        group_by: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict:
        """Execute report from inline parameters (preview mode).

        Round-4 R4-TEN-14 — ``current_user`` is now mandatory. Every
        entity in ``ENTITY_MODEL_MAP`` carries ``tenant_id`` after the
        Phase-3/4 migrations; we inject the predicate unconditionally
        so a manager from tenant A executing a template that lists
        Customer/Quote/Opportunity/Email rows only sees their own
        tenant's data.
        """
        if entity_type not in ENTITY_MODEL_MAP:
            raise BadRequestException(
                f"Gecersiz varlik tipi: {entity_type}. "
                f"Izin verilen: {', '.join(ENTITY_MODEL_MAP.keys())}"
            )

        model, allowed = ENTITY_MODEL_MAP[entity_type]
        # Refuse to execute if the model lacks tenant_id — better to
        # 400 than to silently leak.
        if not hasattr(model, "tenant_id"):
            raise BadRequestException(
                f"'{entity_type}' raporlari guvenli sekilde uretilemez (tenant_id yok)"
            )

        # Separate plain columns from dotted (join) columns
        plain_columns: list[str] = []
        join_columns: list[str] = []
        for col in columns:
            if "." in col:
                join_columns.append(col)
            else:
                plain_columns.append(col)

        self._validate_columns(plain_columns, allowed, entity_type)

        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        # D-035 — shared query composition (no limit/offset). The CSV
        # streaming path reuses this so the two never diverge on tenant
        # scoping, joins, filters, or sort.
        stmt, result_columns = self._build_report_query(
            model=model,
            allowed=allowed,
            entity_type=entity_type,
            plain_columns=plain_columns,
            join_columns=join_columns,
            columns=columns,
            current_user=current_user,
            filters=filters,
            group_by=group_by,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        stmt = stmt.offset(offset).limit(limit)

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self.db.execute(stmt),
                timeout=QUERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise BadRequestException(
                f"Rapor sorgusu zaman asimina ugradi ({QUERY_TIMEOUT_SECONDS}s)"
            )

        raw_rows = result.all()

        # Build response (result_columns comes from _build_report_query).
        if group_by:
            rows = []
            for row in raw_rows:
                row_dict = {group_by: self._serialize_value(row[0]), "count": row[1]}
                for idx, agg_col in enumerate(result_columns[2:], start=2):
                    row_dict[agg_col] = self._serialize_value(row[idx])
                rows.append(row_dict)
            chart_data = {
                "labels": [self._serialize_value(row[0]) for row in raw_rows],
                "values": [row[1] for row in raw_rows],
            }
        else:
            rows = []
            for row in raw_rows:
                row_dict = {}
                for col in plain_columns:
                    row_dict[col] = self._serialize_value(getattr(row, col, None))
                for dotted_col in join_columns:
                    join_entity, join_field = dotted_col.split(".", 1)
                    label = f"{join_entity}_{join_field}"
                    row_dict[dotted_col] = self._serialize_value(
                        getattr(row, label, None)
                    )
                rows.append(row_dict)
            chart_data = None

        return {
            "columns": result_columns,
            "rows": rows,
            "total": len(rows),
            "chart_data": chart_data,
        }

    def _build_report_query(
        self,
        *,
        model,
        allowed: list[str],
        entity_type: str,
        plain_columns: list[str],
        join_columns: list[str],
        columns: list[str],
        current_user,
        filters: list[dict] | None,
        group_by: str | None,
        sort_by: str | None,
        sort_order: str,
    ):
        """Compose the report SELECT (no offset/limit) + its result columns.

        Shared by ``execute_inline`` (paginated/preview) and
        ``stream_report_csv`` (D-035) so tenant scoping, joins, filters,
        and sort can never diverge between the two read paths.
        Returns ``(stmt, result_columns)``.
        """
        # Build column references for the primary entity
        select_cols = [getattr(model, col) for col in plain_columns]

        # Resolve cross-entity joins
        joined_models: set[str] = set()
        join_map = ENTITY_JOINS.get(entity_type, {})
        for dotted_col in join_columns:
            parts = dotted_col.split(".", 1)
            if len(parts) != 2:
                raise BadRequestException(f"Gecersiz sutun formati: {dotted_col}")
            join_entity, join_field = parts
            if join_entity not in join_map:
                raise BadRequestException(
                    f"'{entity_type}' icin '{join_entity}' ile birlesim desteklenmiyor"
                )
            join_cfg = join_map[join_entity]
            if join_field not in join_cfg["columns"]:
                raise BadRequestException(
                    f"'{join_entity}' icin gecersiz sutun: {join_field}. "
                    f"Izin verilen: {', '.join(join_cfg['columns'])}"
                )
            join_model = join_cfg["model"]
            select_cols.append(
                getattr(join_model, join_field).label(f"{join_entity}_{join_field}")
            )
            joined_models.add(join_entity)

        # Handle group_by with aggregation
        result_columns: list[str]
        if group_by:
            self._validate_columns([group_by], allowed, entity_type)
            group_col = getattr(model, group_by)
            agg_cols = [group_col, func.count().label("count")]
            result_columns = [group_by, "count"]
            for col_name in plain_columns:
                if col_name != group_by and col_name in NUMERIC_COLUMNS:
                    col_ref = getattr(model, col_name)
                    agg_cols.append(func.sum(col_ref).label(f"sum_{col_name}"))
                    agg_cols.append(func.avg(col_ref).label(f"avg_{col_name}"))
                    result_columns.append(f"sum_{col_name}")
                    result_columns.append(f"avg_{col_name}")
            stmt = select(*agg_cols).group_by(group_col)
        else:
            stmt = select(*select_cols)
            result_columns = list(columns)

        # Tenant boundary (R4-TEN-14). Injected before joins/filters
        # so neither user input nor the join graph can shadow it.
        stmt = scoped_for_user(stmt, current_user, column=model.tenant_id)

        # Apply joins
        for join_entity in joined_models:
            join_cfg = join_map[join_entity]
            join_model = join_cfg["model"]
            fk_col = getattr(model, join_cfg["fk"])
            stmt = stmt.join(join_model, join_model.id == fk_col, isouter=True)

        # Apply filters
        if filters:
            for f in filters:
                stmt = self._apply_filter(stmt, model, allowed, entity_type, f)

        # Apply sorting
        if sort_by:
            if group_by:
                if sort_by == group_by:
                    sort_col = getattr(model, sort_by)
                else:
                    sort_col = func.count()
            else:
                self._validate_columns([sort_by], allowed, entity_type)
                sort_col = getattr(model, sort_by)
            stmt = stmt.order_by(
                sort_col.asc() if sort_order == "asc" else sort_col.desc()
            )

        return stmt, result_columns

    async def export_csv(self, template_id: int, current_user) -> str:
        """Export report as CSV string (tenant-scoped, R4-TEN-14).

        F-008: every cell passes through ``sanitize_csv_cell`` so a
        customer name like ``=cmd|'/c calc.exe'!A1`` lands in the
        spreadsheet as text instead of an executable formula.

        Buffered path — kept for small reports and as the grouped-report
        fallback. Large row-level exports should use ``stream_report_csv``.
        """
        from app.services.csv_sanitizer import sanitize_csv_row

        data = await self.execute_report(template_id, current_user)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(sanitize_csv_row(data["columns"]))

        for row in data["rows"]:
            writer.writerow(
                sanitize_csv_row([row.get(col, "") for col in data["columns"]])
            )

        return output.getvalue()

    async def stream_report_csv(self, template_id: int, current_user):
        """D-035 — async generator of CSV lines for large exports.

        Instead of buffering every row in a StringIO (which holds the
        whole result set in memory), this streams from the DB cursor
        with ``stream_results=True`` and yields one sanitised CSV line
        at a time. Memory stays flat regardless of row count.

        Grouped/aggregated reports are small by construction; those fall
        back to the buffered ``export_csv`` so we don't complicate the
        cursor path with aggregate row-shaping.

        Yields ``str`` chunks (header first, then one line per row). A
        hard ``MAX_STREAM_ROWS`` cap bounds a runaway export and is
        logged when hit so a truncated file is never mistaken for a
        complete one.
        """
        import csv as _csv
        import io as _io
        import json

        from app.services.csv_sanitizer import sanitize_csv_row

        # Load + tenant-check the template (same contract as execute_report).
        stmt = select(ReportTemplate).where(ReportTemplate.id == template_id)
        template = (await self.db.execute(stmt)).scalar_one_or_none()
        if template is None:
            raise NotFoundException("Rapor sablonu bulunamadi")
        assert_same_tenant(template, current_user, exception_cls=NotFoundException)

        columns = json.loads(template.columns_json)
        filters = json.loads(template.filters_json) if template.filters_json else None
        entity_type = template.entity_type
        group_by = template.group_by

        # Grouped reports are small — defer to the buffered path.
        if group_by:
            yield await self.export_csv(template_id, current_user)
            return

        if entity_type not in ENTITY_MODEL_MAP:
            raise BadRequestException(f"Gecersiz varlik tipi: {entity_type}")
        model, allowed = ENTITY_MODEL_MAP[entity_type]
        if not hasattr(model, "tenant_id"):
            raise BadRequestException(
                f"'{entity_type}' raporlari guvenli sekilde uretilemez (tenant_id yok)"
            )

        plain_columns: list[str] = [c for c in columns if "." not in c]
        join_columns: list[str] = [c for c in columns if "." in c]
        self._validate_columns(plain_columns, allowed, entity_type)

        query, result_columns = self._build_report_query(
            model=model,
            allowed=allowed,
            entity_type=entity_type,
            plain_columns=plain_columns,
            join_columns=join_columns,
            columns=columns,
            current_user=current_user,
            filters=filters,
            group_by=None,
            sort_by=template.sort_by,
            sort_order=template.sort_order,
        )
        query = query.limit(MAX_STREAM_ROWS + 1)

        def _fmt(values: list) -> str:
            buf = _io.StringIO()
            _csv.writer(buf).writerow(sanitize_csv_row(values))
            return buf.getvalue()

        # Header.
        yield _fmt(result_columns)

        emitted = 0
        result = await self.db.stream(query.execution_options(stream_results=True))
        async for row in result:
            if emitted >= MAX_STREAM_ROWS:
                logger.warning(
                    "stream_report_csv truncated template %d at MAX_STREAM_ROWS=%d",
                    template_id, MAX_STREAM_ROWS,
                )
                break
            values = []
            for col in plain_columns:
                values.append(self._serialize_value(getattr(row, col, None)))
            for dotted_col in join_columns:
                join_entity, join_field = dotted_col.split(".", 1)
                values.append(
                    self._serialize_value(
                        getattr(row, f"{join_entity}_{join_field}", None)
                    )
                )
            yield _fmt(values)
            emitted += 1

    def _validate_columns(
        self, columns: list[str], allowed: list[str], entity_type: str
    ) -> None:
        """Validate that all requested columns are in the whitelist."""
        invalid = [col for col in columns if col not in allowed]
        if invalid:
            raise BadRequestException(
                f"'{entity_type}' icin gecersiz sutunlar: {', '.join(invalid)}. "
                f"Izin verilen: {', '.join(allowed)}"
            )

    def _apply_filter(
        self,
        stmt,
        model: type,
        allowed: list[str],
        entity_type: str,
        filter_def: dict,
    ):
        """Apply a single filter to the query statement."""
        field = filter_def.get("field")
        operator = filter_def.get("operator")
        value = filter_def.get("value")

        if not field or not operator:
            raise BadRequestException("Filtre 'field' ve 'operator' alanlari gerektirir")

        self._validate_columns([field], allowed, entity_type)

        if operator not in FILTER_OPERATORS:
            raise BadRequestException(
                f"Gecersiz filtre operatoru: {operator}. "
                f"Izin verilen: {', '.join(FILTER_OPERATORS.keys())}"
            )

        column = getattr(model, field)
        condition = FILTER_OPERATORS[operator](column, value)
        return stmt.where(condition)

    def _serialize_value(self, value) -> str | int | float | bool | None:
        """Serialize a value for JSON response."""
        if value is None:
            return None
        if isinstance(value, (int, float, bool)):
            return value
        return str(value)
