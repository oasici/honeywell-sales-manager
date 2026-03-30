"""Excel/JSON import pipeline with normalization, field mapping, and validation."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

# Turkish character normalization
_TR_FULL_MAP = str.maketrans(
    "\u00e7\u015f\u0131\u011f\u00f6\u00fc\u00c7\u015e\u0130\u011e\u00d6\u00dc",
    "csigouCSIGOU",
)

# Known header keywords that identify the real header row
HEADER_KEYWORDS = {"model number", "model no", "info", "description", "açıklama", "aciklama", "t.p."}

# Field mapping: our field -> possible column header values (normalized)
FIELD_MAPPINGS: dict[str, list[str]] = {
    "info": ["info", "bilgi"],
    "model_number": [
        "model number", "model no", "model", "urun kodu",
        "honeywell code", "honeywell_code", "part number", "parca no",
    ],
    "description_tr": ["aciklama", "tanim", "urun adi", "name_tr"],
    "description_en": ["description", "desc", "name_en", "product name"],
    "transfer_price": [
        "t.p.", "tp", "transfer price", "transfer_price",
        "satis fiyati",
    ],
    "list_price": [
        "list price", "l.p.", "l.p", "lp", "liste fiyati",
    ],
    "supplier_price": [
        "landed", "cost", "supplier price",
        "tedarikci fiyati", "alis fiyati", "maliyet", "net_price",
    ],
    "currency": [
        "currency", "para birimi", "doviz", "kur",
    ],
}


def normalize_text(name: str) -> str:
    """Normalize: lowercase, trim, replace Turkish chars."""
    if not isinstance(name, str):
        return str(name).strip().lower()
    return name.strip().lower().translate(_TR_FULL_MAP)


def parse_price(value: Any) -> float | None:
    """Convert price string to float. Handles: '150 TL', '$200', '1.250,50'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2) if not pd.isna(value) else None
    s = str(value).strip()
    if not s or s == "#REF!" or s == "#N/A" or s == "-":
        return None
    s = re.sub(r'[₺$€£TLUSDEUR\s]', '', s, flags=re.IGNORECASE)
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return round(float(s), 2)
    except (ValueError, TypeError):
        return None


def _read_json_file(file_path: str) -> list[dict]:
    """Read JSON file, handling nested structures."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Find the first array value
        for key, val in data.items():
            if isinstance(val, list):
                logger.info("Found data under key '%s' (%d rows)", key, len(val))
                return val
    return []


def _find_header_row(rows: list[dict]) -> tuple[dict[str, str], int]:
    """Find the real header row in messy Excel data.

    Returns: (column_mapping {generic_col -> real_header_name}, header_row_index)
    """
    for i, row in enumerate(rows[:20]):  # Search first 20 rows
        if not row or not isinstance(row, dict):
            continue
        values = [normalize_text(str(v)) for v in row.values() if v]
        # Check if this row contains header keywords
        matches = sum(1 for v in values if any(kw in v for kw in HEADER_KEYWORDS))
        if matches >= 2:  # At least 2 header keywords found
            # This is the header row - map generic column names to real names
            mapping = {}
            for col_key, col_val in row.items():
                if col_val and str(col_val).strip():
                    mapping[col_key] = str(col_val).strip()

            # Merge sub-header row for columns missing or ambiguous in main header
            if i + 1 < len(rows) and rows[i + 1] and isinstance(rows[i + 1], dict):
                sub = rows[i + 1]
                for col_key, col_val in sub.items():
                    if col_val and str(col_val).strip():
                        val = str(col_val).strip()
                        is_numeric = val.replace('.', '').replace('-', '').replace(',', '').isdigit()
                        if is_numeric or val == "#REF!" or len(val) > 50:
                            continue
                        if col_key not in mapping:
                            # Column not in header - add from sub-header
                            mapping[col_key] = val
                        elif mapping[col_key].lower() in ("supplier", "mounting"):
                            # Ambiguous header - sub-header is more specific
                            mapping[col_key] = val

            logger.info("Found header at row %d with %d columns", i, len(mapping))
            return mapping, i
    return {}, -1


def _map_fields(header_mapping: dict[str, str]) -> dict[str, str]:
    """Map our field names to the generic column keys using header values.

    Priority: alias order (first alias in list has highest priority).
    """
    field_to_col: dict[str, str] = {}

    for field, aliases in FIELD_MAPPINGS.items():
        best_col = None
        best_priority = len(aliases) + 1  # Lower = better

        for col_key, header_val in header_mapping.items():
            norm_header = normalize_text(header_val)
            for priority, alias in enumerate(aliases):
                norm_alias = normalize_text(alias)
                if norm_alias == norm_header or norm_alias in norm_header:
                    if priority < best_priority:
                        best_priority = priority
                        best_col = col_key
                    break

        if best_col:
            field_to_col[field] = best_col

    return field_to_col


def _extract_product(row: dict, field_to_col: dict[str, str]) -> dict | None:
    """Extract product from a single row using field mapping."""
    def get_val(field: str) -> str | None:
        col = field_to_col.get(field)
        if not col or col not in row:
            return None
        val = row[col]
        if val is None:
            return None
        s = str(val).strip()
        return s if s and s != "#REF!" and s != "#N/A" else None

    model = get_val("model_number")
    if not model:
        return None

    currency = get_val("currency")

    return {
        "info": get_val("info"),
        "model_number": model,
        "description_tr": get_val("description_tr"),
        "description_en": get_val("description_en"),
        "transfer_price": parse_price(row.get(field_to_col.get("transfer_price", ""))),
        "list_price": parse_price(row.get(field_to_col.get("list_price", ""))),
        "supplier_price": parse_price(row.get(field_to_col.get("supplier_price", ""))),
        "currency": currency,
    }


async def import_products_from_file(db: AsyncSession, file_path: str) -> dict[str, Any]:
    """Full pipeline: read -> find header -> map fields -> extract -> store."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    # ── Read file ──
    if suffix == ".json":
        rows = _read_json_file(file_path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, dtype=str).fillna("")
        rows = df.to_dict(orient="records")
    elif suffix == ".csv":
        df = pd.read_csv(file_path, dtype=str).fillna("")
        rows = df.to_dict(orient="records")
    else:
        return {"error": f"Unsupported format: {suffix}", "parts_created": 0}

    if not rows:
        return {"error": "Empty file", "parts_created": 0}

    logger.info("Read %d rows from %s", len(rows), suffix)

    # ── Find header row ──
    header_mapping, header_idx = _find_header_row(rows)
    if header_idx < 0:
        # Fallback: treat first row keys as headers (standard Excel)
        if rows[0] and isinstance(rows[0], dict):
            header_mapping = {k: k for k in rows[0].keys()}
            header_idx = 0
            logger.info("No header row found, using column names as headers")
        else:
            return {"error": "Could not find header row", "parts_created": 0}

    # ── Map fields ──
    field_to_col = _map_fields(header_mapping)

    # ── Validate price columns by checking data quality ──
    data_sample = [r for r in rows[header_idx + 2:header_idx + 50] if r and isinstance(r, dict)]
    for price_field in ("transfer_price", "supplier_price"):
        col = field_to_col.get(price_field)
        if not col or not data_sample:
            continue
        # Count how many sample values are #REF! or non-numeric
        bad = sum(1 for r in data_sample if str(r.get(col, "")) in ("#REF!", "#N/A", ""))
        if bad > len(data_sample) * 0.7:
            # This column is mostly bad - look for alternative
            logger.warning("Column %s (%s) has %d/%d bad values, looking for alternative",
                          col, price_field, bad, len(data_sample))
            # Find another column with same header value
            target_header = header_mapping.get(col, "")
            for alt_col, alt_header in header_mapping.items():
                if alt_col != col and normalize_text(alt_header) == normalize_text(target_header):
                    alt_bad = sum(1 for r in data_sample if str(r.get(alt_col, "")) in ("#REF!", "#N/A", ""))
                    if alt_bad < bad:
                        logger.info("Switching %s from %s to %s", price_field, col, alt_col)
                        field_to_col[price_field] = alt_col
                        break

    logger.info("Field mapping: %s", field_to_col)

    if "model_number" not in field_to_col:
        return {
            "error": "Could not find model_number column",
            "parts_created": 0,
            "column_mapping": {k: v for k, v in header_mapping.items() if v},
        }

    # ── Extract products (skip rows before and including header + sub-header) ──
    data_start = header_idx + 1
    # Skip sub-header row
    if data_start < len(rows) and rows[data_start] and isinstance(rows[data_start], dict):
        first_model = rows[data_start].get(field_to_col.get("model_number", ""))
        if first_model and normalize_text(str(first_model)) in ("model no", "tip", "type"):
            data_start += 1

    data_rows = rows[data_start:]

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    current_category: str | None = None

    model_col = field_to_col.get("model_number", "")
    desc_tr_col = field_to_col.get("description_tr", "")
    desc_en_col = field_to_col.get("description_en", "")
    tp_col = field_to_col.get("transfer_price", "")

    for idx, row in enumerate(data_rows):
        if not row or not isinstance(row, dict):
            skipped += 1
            continue

        # Detect section/category headers: only model_number filled, no descriptions or prices
        model_val = row.get(model_col, "")
        has_desc = bool(row.get(desc_tr_col) or row.get(desc_en_col))
        has_price = bool(row.get(tp_col))

        if model_val and not has_desc and not has_price:
            # This is likely a category header row
            current_category = str(model_val).strip()
            skipped += 1
            continue

        product = _extract_product(row, field_to_col)
        if not product:
            skipped += 1
            continue

        # Assign current category
        product["category"] = current_category

        try:
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
                if product.get("list_price") is not None:
                    existing.supplier_price = product["list_price"]
                elif product["supplier_price"] is not None:
                    existing.supplier_price = product["supplier_price"]
                if product.get("currency"):
                    existing.price_currency = product["currency"]
                if product.get("category"):
                    existing.category = product["category"]
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
                    supplier_price=product.get("list_price") or product["supplier_price"],
                    price_currency=product.get("currency"),
                    category=product.get("category"),
                )
                db.add(part)
                created += 1

        except Exception as e:
            if len(errors) < 20:
                errors.append(f"Row {idx + header_idx + 2}: {str(e)[:100]}")

    try:
        await db.flush()
    except Exception as e:
        errors.append(f"DB flush: {str(e)[:200]}")

    logger.info("Import: created=%d updated=%d skipped=%d errors=%d", created, updated, skipped, len(errors))

    # Incrementally update embeddings for new/modified parts only
    embedding_stats: dict = {}
    if created > 0 or updated > 0:
        try:
            from app.services.embedding_service import update_embeddings_incremental

            embedding_stats = await update_embeddings_incremental(db)
            logger.info("Incremental embeddings: %s", embedding_stats)
        except Exception as e:
            logger.warning("Incremental embedding update failed: %s", e)
            embedding_stats = {"error": str(e)}

    return {
        "parts_created": created,
        "parts_updated": updated,
        "skipped": skipped,
        "errors": errors[:20],
        "column_mapping": field_to_col,
        "embeddings": embedding_stats,
    }
