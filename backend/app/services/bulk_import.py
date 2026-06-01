"""F-021 lite — synchronous CSV import for customers + parts.

At 20-30 users scale, "bulk import" really means "ops uploads the
50-500 row CSV they've been keeping in Excel." That's well within
synchronous-handling territory — no need for a background-job
framework, no progress polling. A single POST with the CSV file
streamed in returns a report.

Two entity types supported today; the dispatch pattern allows
adding more (opportunities, parts pricing, etc.) by registering a
handler tuple.

Each import is *all-or-nothing per row* — a row failing validation
is reported but doesn't roll back successful peers. The DB writes
go in batches of 50 inside the same transaction; if the entire
job blows up halfway we rollback the open transaction and report.

Idempotency: each importable entity declares its natural key
(``customers.vergi_no``, ``spare_parts.part_code``). Duplicates
become updates instead of insert errors — operators upload the same
sheet twice without surprise.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_MAX_ROWS = 10_000              # synchronous-handling safety cap
_BATCH_SIZE = 50


@dataclass
class ImportError:
    row: int           # 1-based row number in the CSV (line 1 = header)
    field: str | None  # which field caused the error, if known
    message: str


@dataclass
class ImportReport:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ImportError] = field(default_factory=list)
    total_seen: int = 0

    def as_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": [
                {"row": e.row, "field": e.field, "message": e.message}
                for e in self.errors
            ],
            "total_seen": self.total_seen,
        }


# ── Helpers ─────────────────────────────────────────────────────────


def _norm(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


# ── Customer import ────────────────────────────────────────────────


REQUIRED_CUSTOMER_FIELDS = ("name", "vergi_no")
CUSTOMER_OPTIONAL_FIELDS = ("email", "phone", "industry", "city", "tier")


async def import_customers(
    db: AsyncSession,
    csv_text: str,
    *,
    tenant_id: int,
    actor_id: int,
) -> ImportReport:
    """CSV columns expected: name, vergi_no, email, phone, industry, city, tier.

    Order doesn't matter — DictReader honours header row. Extra columns
    are ignored. Missing required columns abort the whole upload.

    Vergi_no is the natural key; duplicate vergi_no in the same tenant
    becomes UPDATE (the row carries the new values).
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        report.errors.append(ImportError(row=1, field=None, message="csv_empty"))
        return report
    missing = set(REQUIRED_CUSTOMER_FIELDS) - set(reader.fieldnames)
    if missing:
        report.errors.append(
            ImportError(
                row=1, field=None,
                message=f"csv_missing_required_columns:{sorted(missing)}",
            )
        )
        return report

    rows_to_apply: list[dict] = []
    for idx, raw in enumerate(reader, start=2):
        report.total_seen += 1
        if report.total_seen > _MAX_ROWS:
            report.errors.append(
                ImportError(
                    row=idx, field=None,
                    message=f"row_cap_exceeded:{_MAX_ROWS}",
                )
            )
            break

        name = _norm(raw.get("name"))
        vergi_no = _norm(raw.get("vergi_no"))
        if not name:
            report.errors.append(ImportError(row=idx, field="name", message="required"))
            report.skipped += 1
            continue
        if not vergi_no:
            report.errors.append(ImportError(row=idx, field="vergi_no", message="required"))
            report.skipped += 1
            continue
        if not (10 <= len(vergi_no) <= 11) or not vergi_no.isdigit():
            report.errors.append(
                ImportError(
                    row=idx, field="vergi_no",
                    message="must_be_10_or_11_digits",
                )
            )
            report.skipped += 1
            continue

        rows_to_apply.append(
            {
                "tenant_id": tenant_id,
                "name": name,
                "vergi_no": vergi_no,
                "email": _norm(raw.get("email")),
                "phone": _norm(raw.get("phone")),
                "industry": _norm(raw.get("industry")),
                "city": _norm(raw.get("city")),
                "tier": _norm(raw.get("tier")) or "Bronze",
                "created_by": actor_id,
            }
        )

    # Apply in batches inside one transaction.
    for batch_start in range(0, len(rows_to_apply), _BATCH_SIZE):
        batch = rows_to_apply[batch_start : batch_start + _BATCH_SIZE]
        for row in batch:
            try:
                # Look up by (tenant_id, vergi_no) — partial unique
                # ignores soft-deleted rows so a previously-deleted
                # customer can be re-imported.
                existing = (
                    await db.execute(
                        text(
                            """
                            SELECT id FROM customers
                            WHERE tenant_id = :tenant_id
                              AND vergi_no = :vergi_no
                              AND deleted_at IS NULL
                            """
                        ),
                        {"tenant_id": row["tenant_id"], "vergi_no": row["vergi_no"]},
                    )
                ).first()
                if existing:
                    await db.execute(
                        text(
                            """
                            UPDATE customers
                               SET name = :name,
                                   email = COALESCE(:email, email),
                                   phone = COALESCE(:phone, phone),
                                   industry = COALESCE(:industry, industry),
                                   city = COALESCE(:city, city),
                                   tier = COALESCE(:tier, tier)
                             WHERE id = :id
                            """
                        ),
                        {**row, "id": existing[0]},
                    )
                    report.updated += 1
                else:
                    await db.execute(
                        text(
                            """
                            INSERT INTO customers
                              (tenant_id, name, vergi_no, email, phone,
                               industry, city, tier, created_by)
                            VALUES
                              (:tenant_id, :name, :vergi_no, :email, :phone,
                               :industry, :city, :tier, :created_by)
                            """
                        ),
                        row,
                    )
                    report.inserted += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    ImportError(
                        row=batch_start + 1,
                        field=None,
                        message=f"db_error: {str(exc)[:200]}",
                    )
                )
                report.skipped += 1
                logger.warning(
                    "Customer import row failed: %s", str(exc)[:300]
                )
        await db.flush()

    return report


# ── Spare-part import ──────────────────────────────────────────────


REQUIRED_PART_FIELDS = ("part_code", "description")
PART_OPTIONAL_FIELDS = ("category", "list_price", "currency", "min_stock")


REQUIRED_LEAD_FIELDS = ("first_name", "last_name", "email")
LEAD_OPTIONAL_FIELDS = ("phone", "company", "title", "source")


async def import_leads(
    db: AsyncSession,
    csv_text: str,
    *,
    tenant_id: int,
    actor_id: int,
) -> ImportReport:
    """CSV columns: first_name, last_name, email, phone, company, title, source.

    Natural key: (tenant_id, lower(email)). Duplicate email becomes
    UPDATE. Source defaults to ``import`` when omitted.
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        report.errors.append(ImportError(row=1, field=None, message="csv_empty"))
        return report
    missing = set(REQUIRED_LEAD_FIELDS) - set(reader.fieldnames)
    if missing:
        report.errors.append(
            ImportError(
                row=1, field=None,
                message=f"csv_missing_required_columns:{sorted(missing)}",
            )
        )
        return report

    rows_to_apply: list[dict] = []
    for idx, raw in enumerate(reader, start=2):
        report.total_seen += 1
        if report.total_seen > _MAX_ROWS:
            report.errors.append(
                ImportError(row=idx, field=None, message=f"row_cap_exceeded:{_MAX_ROWS}")
            )
            break

        first = _norm(raw.get("first_name"))
        last = _norm(raw.get("last_name"))
        email = _norm(raw.get("email"))
        if not first or not last:
            report.errors.append(ImportError(row=idx, field="name", message="required"))
            report.skipped += 1
            continue
        if not email or "@" not in email:
            report.errors.append(ImportError(row=idx, field="email", message="invalid"))
            report.skipped += 1
            continue

        rows_to_apply.append(
            {
                "tenant_id": tenant_id,
                "first_name": first,
                "last_name": last,
                "email": email.lower(),
                "phone": _norm(raw.get("phone")),
                "company": _norm(raw.get("company")),
                "title": _norm(raw.get("title")),
                "source": _norm(raw.get("source")) or "import",
                "owner_id": actor_id,
                "status": "new",
            }
        )

    for batch_start in range(0, len(rows_to_apply), _BATCH_SIZE):
        batch = rows_to_apply[batch_start : batch_start + _BATCH_SIZE]
        for row in batch:
            # Per-row SAVEPOINT so one failing row doesn't poison the
            # whole batch with "current transaction is aborted".
            try:
                async with db.begin_nested():
                    existing = (
                        await db.execute(
                            text(
                                """
                                SELECT id FROM leads
                                WHERE tenant_id = :tenant_id AND LOWER(email) = :email
                                  AND deleted_at IS NULL
                                """
                            ),
                            {"tenant_id": row["tenant_id"], "email": row["email"]},
                        )
                    ).first()
                    if existing:
                        await db.execute(
                            text(
                                """
                                UPDATE leads
                                   SET first_name = :first_name,
                                       last_name  = :last_name,
                                       phone      = COALESCE(:phone, phone),
                                       company    = COALESCE(:company, company),
                                       title      = COALESCE(:title, title),
                                       source     = COALESCE(:source, source)
                                 WHERE id = :id
                                """
                            ),
                            {**row, "id": existing[0]},
                        )
                        report.updated += 1
                    else:
                        await db.execute(
                            text(
                                """
                                INSERT INTO leads
                                  (tenant_id, first_name, last_name, email, phone,
                                   company, title, source, owner_id, status, lead_score,
                                   created_at, updated_at)
                                VALUES
                                  (:tenant_id, :first_name, :last_name, :email, :phone,
                                   :company, :title, :source, :owner_id, :status, 0,
                                   now(), now())
                                """
                            ),
                            row,
                        )
                        report.inserted += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    ImportError(
                        row=batch_start + 1,
                        field=None,
                        message=f"db_error: {str(exc)[:200]}",
                    )
                )
                report.skipped += 1

    return report


# ── Opportunity import (D-031 second half) ─────────────────────────


REQUIRED_OPP_FIELDS = ("title", "customer_vergi_no")
OPP_OPTIONAL_FIELDS = (
    "amount", "currency", "stage", "close_date", "probability", "source",
)
_VALID_STAGES = {
    "prospecting", "qualified", "proposal", "negotiation",
    "closed_won", "closed_lost",
}
_STAGE_DEFAULT_PROBABILITY = {
    "prospecting": 10.0,
    "qualified": 25.0,
    "proposal": 50.0,
    "negotiation": 75.0,
    "closed_won": 100.0,
    "closed_lost": 0.0,
}


def _parse_amount(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    # Tolerate Turkish-locale decimals ("1.234,56") and plain floats.
    cleaned = raw.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_close_date(raw: str | None):
    """Accept ISO (2026-08-15) or DD/MM/YYYY. Returns a ``date`` or None.

    asyncpg's prepared-statement plan requires a python ``date`` when
    the column is DATE — a CAST-from-text bind raises
    ``'str' object has no attribute 'toordinal'``.
    """
    from datetime import datetime as _dt

    if raw is None or not raw.strip():
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return _dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


async def import_opportunities(
    db: AsyncSession,
    csv_text: str,
    *,
    tenant_id: int,
    actor_id: int,
) -> ImportReport:
    """D-031 (opportunities half).

    CSV columns:
      Required: ``title``, ``customer_vergi_no``
      Optional: ``amount`` (decimal, TR or US format), ``currency``
                (default TRY), ``stage`` (default prospecting),
                ``close_date`` (ISO / DD-MM-YYYY), ``probability``
                (0-100; auto from stage when blank), ``source``.

    Natural key: (tenant_id, title, customer_id). Duplicates update;
    avoids re-inserting the same forecast row when an operator
    uploads a refreshed CSV. ``customer_vergi_no`` is resolved to
    ``customer_id`` per row; missing customer = row skipped (caller
    must import customers first).
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        report.errors.append(ImportError(row=1, field=None, message="csv_empty"))
        return report
    missing = set(REQUIRED_OPP_FIELDS) - set(reader.fieldnames)
    if missing:
        report.errors.append(
            ImportError(
                row=1, field=None,
                message=f"csv_missing_required_columns:{sorted(missing)}",
            )
        )
        return report

    rows_to_apply: list[dict] = []
    for idx, raw in enumerate(reader, start=2):
        report.total_seen += 1
        if report.total_seen > _MAX_ROWS:
            report.errors.append(
                ImportError(row=idx, field=None, message=f"row_cap_exceeded:{_MAX_ROWS}")
            )
            break

        title = _norm(raw.get("title"))
        vergi = _norm(raw.get("customer_vergi_no"))
        if not title:
            report.errors.append(ImportError(row=idx, field="title", message="required"))
            report.skipped += 1
            continue
        if not vergi:
            report.errors.append(
                ImportError(row=idx, field="customer_vergi_no", message="required")
            )
            report.skipped += 1
            continue

        stage = (_norm(raw.get("stage")) or "prospecting").lower()
        if stage not in _VALID_STAGES:
            report.errors.append(
                ImportError(
                    row=idx, field="stage",
                    message=f"invalid_stage:{stage}",
                )
            )
            report.skipped += 1
            continue

        prob_raw = _norm(raw.get("probability"))
        if prob_raw is None:
            probability = _STAGE_DEFAULT_PROBABILITY[stage]
        else:
            try:
                probability = float(prob_raw)
            except ValueError:
                report.errors.append(
                    ImportError(row=idx, field="probability", message="not_a_number")
                )
                report.skipped += 1
                continue
            if probability < 0 or probability > 100:
                report.errors.append(
                    ImportError(row=idx, field="probability", message="out_of_range")
                )
                report.skipped += 1
                continue

        rows_to_apply.append(
            {
                "tenant_id": tenant_id,
                "title": title,
                "customer_vergi_no": vergi,
                "amount": _parse_amount(raw.get("amount")),
                "currency": _norm(raw.get("currency")) or "TRY",
                "stage": stage,
                "close_date": _parse_close_date(raw.get("close_date")),
                "probability": probability,
                "source": _norm(raw.get("source")),
                "owner_id": actor_id,
                "_row_idx": idx,
            }
        )

    for batch_start in range(0, len(rows_to_apply), _BATCH_SIZE):
        batch = rows_to_apply[batch_start : batch_start + _BATCH_SIZE]
        for row in batch:
            row_idx = row.pop("_row_idx")
            # SAVEPOINT per row so one bad customer lookup doesn't
            # poison the rest of the batch (matches lead-import pattern).
            try:
                async with db.begin_nested():
                    # Customer table stores the Turkish tax number in
                    # `tax_id`; the CSV column stays user-friendly as
                    # ``customer_vergi_no`` since that's the term operators
                    # see in the rest of the UI.
                    cust = (
                        await db.execute(
                            text(
                                """
                                SELECT id FROM customers
                                WHERE tenant_id = :t AND tax_id = :v
                                  AND deleted_at IS NULL
                                """
                            ),
                            {"t": row["tenant_id"], "v": row["customer_vergi_no"]},
                        )
                    ).first()
                    if not cust:
                        raise ValueError(
                            f"customer_not_found:vergi_no={row['customer_vergi_no']}"
                        )
                    customer_id = cust[0]

                    existing = (
                        await db.execute(
                            text(
                                """
                                SELECT id FROM opportunities
                                WHERE tenant_id = :t AND title = :title
                                  AND customer_id = :cid
                                  AND deleted_at IS NULL
                                """
                            ),
                            {"t": row["tenant_id"], "title": row["title"], "cid": customer_id},
                        )
                    ).first()

                    payload = {
                        "tenant_id": row["tenant_id"],
                        "title": row["title"],
                        "customer_id": customer_id,
                        "amount": row["amount"],
                        "currency": row["currency"],
                        "stage": row["stage"],
                        "close_date": row["close_date"],
                        "probability": row["probability"],
                        "source": row["source"],
                        "owner_id": row["owner_id"],
                    }
                    if existing:
                        await db.execute(
                            text(
                                """
                                UPDATE opportunities
                                   SET amount      = COALESCE(:amount, amount),
                                       currency    = :currency,
                                       stage       = :stage,
                                       close_date  = COALESCE(:close_date, close_date),
                                       probability = :probability,
                                       source      = COALESCE(:source, source),
                                       updated_at  = now()
                                 WHERE id = :id
                                """
                            ),
                            {**payload, "id": existing[0]},
                        )
                        report.updated += 1
                    else:
                        await db.execute(
                            text(
                                """
                                INSERT INTO opportunities
                                  (tenant_id, title, customer_id, amount, currency,
                                   stage, close_date, probability, source, owner_id,
                                   status, row_version, created_at, updated_at)
                                VALUES
                                  (:tenant_id, :title, :customer_id, :amount, :currency,
                                   :stage, :close_date, :probability, :source,
                                   :owner_id, 'active', 1, now(), now())
                                """
                            ),
                            payload,
                        )
                        report.inserted += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    ImportError(
                        row=row_idx,
                        field=None,
                        message=f"db_error: {str(exc)[:200]}",
                    )
                )
                report.skipped += 1

    return report


async def import_parts(
    db: AsyncSession,
    csv_text: str,
    *,
    tenant_id: int,
    actor_id: int,
) -> ImportReport:
    """CSV columns: part_code, description, category, list_price, currency, min_stock.

    Natural key: (tenant_id, part_code). Duplicates update.
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        report.errors.append(ImportError(row=1, field=None, message="csv_empty"))
        return report
    missing = set(REQUIRED_PART_FIELDS) - set(reader.fieldnames)
    if missing:
        report.errors.append(
            ImportError(
                row=1, field=None,
                message=f"csv_missing_required_columns:{sorted(missing)}",
            )
        )
        return report

    rows_to_apply: list[dict] = []
    for idx, raw in enumerate(reader, start=2):
        report.total_seen += 1
        if report.total_seen > _MAX_ROWS:
            report.errors.append(
                ImportError(
                    row=idx, field=None,
                    message=f"row_cap_exceeded:{_MAX_ROWS}",
                )
            )
            break

        code = _norm(raw.get("part_code"))
        desc = _norm(raw.get("description"))
        if not code:
            report.errors.append(ImportError(row=idx, field="part_code", message="required"))
            report.skipped += 1
            continue
        if not desc:
            report.errors.append(ImportError(row=idx, field="description", message="required"))
            report.skipped += 1
            continue

        list_price = _norm(raw.get("list_price"))
        if list_price is not None:
            try:
                list_price = float(list_price.replace(",", "."))
            except ValueError:
                report.errors.append(
                    ImportError(
                        row=idx, field="list_price",
                        message="must_be_number",
                    )
                )
                report.skipped += 1
                continue

        rows_to_apply.append(
            {
                "tenant_id": tenant_id,
                "part_code": code,
                "description": desc,
                "category": _norm(raw.get("category")),
                "list_price": list_price,
                "currency": _norm(raw.get("currency")) or "TRY",
                "min_stock": int(raw.get("min_stock") or 0) if raw.get("min_stock") else 0,
            }
        )

    for batch_start in range(0, len(rows_to_apply), _BATCH_SIZE):
        batch = rows_to_apply[batch_start : batch_start + _BATCH_SIZE]
        for row in batch:
            try:
                existing = (
                    await db.execute(
                        text(
                            """
                            SELECT id FROM spare_parts
                            WHERE tenant_id = :tenant_id
                              AND part_code = :part_code
                            """
                        ),
                        {"tenant_id": row["tenant_id"], "part_code": row["part_code"]},
                    )
                ).first()
                if existing:
                    await db.execute(
                        text(
                            """
                            UPDATE spare_parts
                               SET description = :description,
                                   category    = COALESCE(:category, category),
                                   list_price  = COALESCE(:list_price, list_price),
                                   currency    = COALESCE(:currency, currency),
                                   min_stock   = COALESCE(:min_stock, min_stock)
                             WHERE id = :id
                            """
                        ),
                        {**row, "id": existing[0]},
                    )
                    report.updated += 1
                else:
                    await db.execute(
                        text(
                            """
                            INSERT INTO spare_parts
                              (tenant_id, part_code, description, category,
                               list_price, currency, min_stock)
                            VALUES
                              (:tenant_id, :part_code, :description, :category,
                               :list_price, :currency, :min_stock)
                            """
                        ),
                        row,
                    )
                    report.inserted += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append(
                    ImportError(
                        row=batch_start + 1,
                        field=None,
                        message=f"db_error: {str(exc)[:200]}",
                    )
                )
                report.skipped += 1
        await db.flush()

    return report
