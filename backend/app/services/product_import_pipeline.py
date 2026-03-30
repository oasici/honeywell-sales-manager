"""Excel import pipeline with normalization, field mapping, and validation."""

import logging
import re
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

# Turkish character normalization
TR_CHAR_MAP = str.maketrans("csigouCSIGOU", "csigouCSIGOU")
_TR_FULL_MAP = str.maketrans(
    "\u00e7\u015f\u0131\u011f\u00f6\u00fc\u00c7\u015e\u0130\u011e\u00d6\u00dc",
    "csigouCSIGOU",
)

# Field mapping rules - normalized column name -> our field name
FIELD_MAPPINGS: dict[str, list[str]] = {
    "info": ["info", "bilgi"],
    "model_number": [
        "model number",
        "model no",
        "model",
        "urun kodu",
        "honeywell code",
        "honeywell_code",
        "part number",
        "parca no",
    ],
    "description_tr": ["aciklama", "tanim", "urun adi", "name_tr"],
    "description_en": ["description", "desc", "name_en", "product name"],
    "transfer_price": [
        "t.p.",
        "tp",
        "transfer price",
        "transfer_price",
        "list_price",
        "list price",
        "satis fiyati",
    ],
    "supplier_price": [
        "supplier price",
        "tedarikci fiyati",
        "alis fiyati",
        "maliyet",
        "cost",
        "net_price",
    ],
}


def normalize_column_name(name: str) -> str:
    """Normalize column name: lowercase, trim, replace Turkish chars."""
    if not isinstance(name, str):
        return str(name).strip().lower()
    return (
        name.strip()
        .lower()
        .translate(_TR_FULL_MAP)
        .replace("_", " ")
        .strip()
    )


def parse_price(value: Any) -> float | None:
    """Convert price string to float.

    Handles formats like '150 TL', '$200', '1.250,50', plain numbers.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    s = str(value).strip()
    if not s:
        return None

    # Remove currency symbols and text
    s = re.sub(r"[\u20ba$\u20ac\u00a3TLUSDEUR\s]", "", s, flags=re.IGNORECASE)

    # Handle Turkish number format: 1.250,50 -> 1250.50
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return round(float(s), 2)
    except (ValueError, TypeError):
        return None


def map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map DataFrame columns to our field names using semantic matching."""
    normalized = {normalize_column_name(col): col for col in df.columns}
    mapping: dict[str, str] = {}

    for field, aliases in FIELD_MAPPINGS.items():
        for alias in aliases:
            norm_alias = normalize_column_name(alias)
            # Exact match
            if norm_alias in normalized:
                mapping[field] = normalized[norm_alias]
                break
            # Partial match
            for norm_col, orig_col in normalized.items():
                if norm_alias in norm_col or norm_col in norm_alias:
                    if field not in mapping:
                        mapping[field] = orig_col
                        break
        # If we matched via partial, the inner break only exits the inner loop.
        # The outer for-alias loop continues but mapping[field] is already set,
        # so subsequent iterations won't overwrite thanks to the `if field not in mapping` guard.

    return mapping


def extract_product(
    row: pd.Series,
    col_mapping: dict[str, str],
) -> dict[str, Any] | None:
    """Extract and normalize a single product from a DataFrame row."""

    def get_val(field: str) -> str | None:
        col = col_mapping.get(field)
        if not col:
            return None
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        return s if s else None

    model_number = get_val("model_number")
    if not model_number:
        return None  # model_number is required

    tp_col = col_mapping.get("transfer_price", "")
    sp_col = col_mapping.get("supplier_price", "")

    return {
        "info": get_val("info"),
        "model_number": model_number,
        "description_tr": get_val("description_tr"),
        "description_en": get_val("description_en"),
        "transfer_price": parse_price(row.get(tp_col) if tp_col else None),
        "supplier_price": parse_price(row.get(sp_col) if sp_col else None),
    }


async def import_products_from_file(
    db: AsyncSession,
    file_path: str,
) -> dict[str, Any]:
    """Full import pipeline: read -> normalize -> map -> validate -> store."""
    from pathlib import Path

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, dtype=str).fillna("")
    elif suffix == ".csv":
        df = pd.read_csv(file_path, dtype=str).fillna("")
    else:
        return {"error": f"Unsupported format: {suffix}", "imported": 0}

    # Remove completely empty rows
    df = df.dropna(how="all").reset_index(drop=True)

    # Map columns
    col_mapping = map_columns(df)
    logger.info("Column mapping: %s", col_mapping)

    if "model_number" not in col_mapping:
        return {
            "error": "Could not find model_number column",
            "imported": 0,
            "column_mapping": col_mapping,
        }

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    max_errors = 20

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-based header + 1-based data)
        product = extract_product(row, col_mapping)

        if not product:
            skipped += 1
            continue

        try:
            # Check if exists by model_number or honeywell_code
            result = await db.execute(
                select(SparePart).where(
                    (SparePart.model_number == product["model_number"])
                    | (SparePart.honeywell_code == product["model_number"])
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                if product["info"]:
                    existing.info = product["info"]
                if product["description_tr"]:
                    existing.name_tr = product["description_tr"]
                    existing.description_tr = product["description_tr"]
                if product["description_en"]:
                    existing.name_en = product["description_en"]
                    existing.description_en = product["description_en"]
                if product["transfer_price"] is not None:
                    existing.transfer_price = product["transfer_price"]
                if product["supplier_price"] is not None:
                    existing.supplier_price = product["supplier_price"]
                if not existing.model_number:
                    existing.model_number = product["model_number"]
                updated += 1
            else:
                part = SparePart(
                    honeywell_code=product["model_number"],
                    model_number=product["model_number"],
                    info=product["info"],
                    name_tr=product["description_tr"],
                    name_en=product["description_en"],
                    description_tr=product["description_tr"],
                    description_en=product["description_en"],
                    transfer_price=product["transfer_price"],
                    supplier_price=product["supplier_price"],
                )
                db.add(part)
                created += 1

        except Exception as e:
            if len(errors) < max_errors:
                errors.append(f"Row {row_num}: {str(e)[:100]}")

    try:
        await db.flush()
    except Exception as e:
        errors.append(f"DB flush error: {str(e)[:200]}")

    logger.info(
        "Product import: created=%d, updated=%d, skipped=%d, errors=%d",
        created,
        updated,
        skipped,
        len(errors),
    )

    return {
        "parts_created": created,
        "parts_updated": updated,
        "skipped": skipped,
        "errors": errors[:max_errors],
        "column_mapping": col_mapping,
    }
