"""Excel/CSV import service for spare parts, prices, and customers."""

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.price_entry import PriceEntry
from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)


def _read_file(file_path: str) -> pd.DataFrame:
    """Read an Excel or CSV file into a DataFrame."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(file_path, dtype=str).fillna("")
    elif suffix == ".csv":
        return pd.read_csv(file_path, dtype=str).fillna("")
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .xlsx, .xls, or .csv")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names: strip, lower, replace spaces with underscores."""
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
    return df


async def import_catalog_from_file(db: AsyncSession, file_path: str) -> dict[str, Any]:
    """Import spare parts + prices from a single Excel/CSV file.

    Each row contains both part info and price info side by side.
    Part is upserted by honeywell_code, then a PriceEntry is created if
    price columns are present.

    Expected columns:
      Required: honeywell_code
      Part info: name_en, name_tr, description_en, description_tr, category, subcategory
      Price info: list_price, discount_pct, net_price, currency, valid_from, valid_until

    Returns: {parts_created, parts_updated, prices_created, errors}
    """
    parts_created = 0
    parts_updated = 0
    prices_created = 0
    errors: list[str] = []

    try:
        df = _read_file(file_path)
        df = _normalize_columns(df)
    except Exception as exc:
        return {
            "parts_created": 0, "parts_updated": 0,
            "prices_created": 0, "errors": [f"File read error: {exc}"],
        }

    if "honeywell_code" not in df.columns:
        return {
            "parts_created": 0, "parts_updated": 0,
            "prices_created": 0, "errors": ["Missing required column: honeywell_code"],
        }

    has_price_col = "list_price" in df.columns

    for idx, row in df.iterrows():
        row_num = idx + 2
        code = str(row.get("honeywell_code", "")).strip()
        if not code:
            errors.append(f"Row {row_num}: empty honeywell_code, skipped")
            continue

        try:
            # --- Upsert SparePart ---
            stmt = select(SparePart).where(SparePart.honeywell_code == code)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            part_fields = {
                "name_en": str(row.get("name_en", "")).strip() or None,
                "name_tr": str(row.get("name_tr", "")).strip() or None,
                "description_en": str(row.get("description_en", "")).strip() or None,
                "description_tr": str(row.get("description_tr", "")).strip() or None,
                "category": str(row.get("category", "")).strip() or None,
                "subcategory": str(row.get("subcategory", "")).strip() or None,
            }

            if existing:
                for key, value in part_fields.items():
                    if value is not None:
                        setattr(existing, key, value)
                parts_updated += 1
                part = existing
            else:
                part = SparePart(honeywell_code=code, **part_fields)
                db.add(part)
                parts_created += 1
                await db.flush()  # get part.id

            # --- Create PriceEntry if price columns exist ---
            if has_price_col:
                raw_price = str(row.get("list_price", "")).strip()
                if raw_price:
                    list_price = float(raw_price)
                    discount_pct = float(row.get("discount_pct", 0) or 0)
                    net_price_raw = str(row.get("net_price", "")).strip()
                    if net_price_raw:
                        net_price = float(net_price_raw)
                    else:
                        net_price = round(list_price * (1 - discount_pct / 100), 2)

                    currency = str(row.get("currency", "USD")).strip().upper() or "USD"
                    valid_from = _parse_date(row.get("valid_from", ""))
                    valid_until = _parse_date(row.get("valid_until", ""))

                    entry = PriceEntry(
                        spare_part_id=part.id,
                        list_price=list_price,
                        discount_pct=discount_pct,
                        net_price=net_price,
                        currency=currency,
                        valid_from=valid_from,
                        valid_until=valid_until,
                    )
                    db.add(entry)
                    prices_created += 1

        except Exception as exc:
            errors.append(f"Row {row_num} ({code}): {exc}")

    try:
        await db.flush()
    except Exception as exc:
        errors.append(f"Database flush error: {exc}")

    logger.info(
        "Catalog import: parts created=%d, updated=%d, prices=%d, errors=%d",
        parts_created, parts_updated, prices_created, len(errors),
    )
    return {
        "parts_created": parts_created,
        "parts_updated": parts_updated,
        "prices_created": prices_created,
        "errors": errors,
    }


async def import_prices_from_file(
    db: AsyncSession, file_path: str, version: str = ""
) -> dict[str, Any]:
    """Import price entries from Excel/CSV.

    Expected columns: honeywell_code, list_price, discount_pct, net_price,
    currency, valid_from, valid_until.

    Returns: {created: int, errors: list[str]}
    """
    created = 0
    errors: list[str] = []

    try:
        df = _read_file(file_path)
        df = _normalize_columns(df)
    except Exception as exc:
        return {"created": 0, "errors": [f"File read error: {exc}"]}

    required_cols = {"honeywell_code", "list_price"}
    missing = required_cols - set(df.columns)
    if missing:
        return {"created": 0, "errors": [f"Missing required columns: {missing}"]}

    for idx, row in df.iterrows():
        row_num = idx + 2
        code = str(row.get("honeywell_code", "")).strip()
        if not code:
            errors.append(f"Row {row_num}: empty honeywell_code, skipped")
            continue

        try:
            # Find the spare part
            stmt = select(SparePart).where(SparePart.honeywell_code == code)
            result = await db.execute(stmt)
            part = result.scalar_one_or_none()

            if not part:
                errors.append(f"Row {row_num}: spare part '{code}' not found")
                continue

            list_price = float(row.get("list_price", 0))
            discount_pct = float(row.get("discount_pct", 0) or 0)
            net_price_raw = row.get("net_price", "")
            if net_price_raw and str(net_price_raw).strip():
                net_price = float(net_price_raw)
            else:
                net_price = round(list_price * (1 - discount_pct / 100), 2)

            currency = str(row.get("currency", "USD")).strip() or "USD"

            valid_from = _parse_date(row.get("valid_from", ""))
            valid_until = _parse_date(row.get("valid_until", ""))

            entry = PriceEntry(
                spare_part_id=part.id,
                list_price=list_price,
                discount_pct=discount_pct,
                net_price=net_price,
                currency=currency.upper(),
                valid_from=valid_from,
                valid_until=valid_until,
                price_list_version=version or None,
            )
            db.add(entry)
            created += 1

        except Exception as exc:
            errors.append(f"Row {row_num} ({code}): {exc}")

    try:
        await db.flush()
    except Exception as exc:
        errors.append(f"Database flush error: {exc}")

    logger.info("Prices import: created=%d, errors=%d", created, len(errors))
    return {"created": created, "errors": errors}


async def import_customers_from_file(
    db: AsyncSession, file_path: str
) -> dict[str, Any]:
    """Import customers from Excel/CSV. Upsert by email.

    Expected columns: email, name, company, phone, address, tax_id, preferred_lang.

    Returns: {created: int, updated: int, errors: list[str]}
    """
    created = 0
    updated = 0
    errors: list[str] = []

    try:
        df = _read_file(file_path)
        df = _normalize_columns(df)
    except Exception as exc:
        return {"created": 0, "updated": 0, "errors": [f"File read error: {exc}"]}

    required_cols = {"email", "name"}
    missing = required_cols - set(df.columns)
    if missing:
        return {"created": 0, "updated": 0, "errors": [f"Missing required columns: {missing}"]}

    for idx, row in df.iterrows():
        row_num = idx + 2
        email = str(row.get("email", "")).strip().lower()
        name = str(row.get("name", "")).strip()

        if not email:
            errors.append(f"Row {row_num}: empty email, skipped")
            continue
        if not name:
            errors.append(f"Row {row_num}: empty name, skipped")
            continue

        try:
            stmt = select(Customer).where(Customer.email == email)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            fields = {
                "name": name,
                "company": str(row.get("company", "")).strip() or None,
                "phone": str(row.get("phone", "")).strip() or None,
                "address": str(row.get("address", "")).strip() or None,
                "tax_id": str(row.get("tax_id", "")).strip() or None,
                "preferred_lang": str(row.get("preferred_lang", "tr")).strip() or "tr",
            }

            if existing:
                for key, value in fields.items():
                    if value is not None:
                        setattr(existing, key, value)
                updated += 1
            else:
                customer = Customer(email=email, **fields)
                db.add(customer)
                created += 1

        except Exception as exc:
            errors.append(f"Row {row_num} ({email}): {exc}")

    try:
        await db.flush()
    except Exception as exc:
        errors.append(f"Database flush error: {exc}")

    logger.info(
        "Customers import: created=%d, updated=%d, errors=%d",
        created, updated, len(errors),
    )
    return {"created": created, "updated": updated, "errors": errors}


def _parse_date(value: Any):
    """Parse a date string to date object, or return None."""
    if not value or not str(value).strip():
        return None
    from datetime import date, datetime

    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
