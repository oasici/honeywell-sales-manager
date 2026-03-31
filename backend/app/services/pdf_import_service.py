"""Extract parts and quote data from PDF files using pdfplumber."""

import logging
import re

import pdfplumber

logger = logging.getLogger(__name__)

# Header keywords to identify parts table columns
_HEADER_ALIASES = {
    "sira": "row_num",
    "sıra": "row_num",
    "#": "row_num",
    "no": "row_num",
    "adet": "quantity",
    "qty": "quantity",
    "miktar": "quantity",
    "pn": "honeywell_code",
    "part": "honeywell_code",
    "parca": "honeywell_code",
    "parça": "honeywell_code",
    "model": "honeywell_code",
    "kod": "honeywell_code",
    "code": "honeywell_code",
    "aciklama": "description",
    "açıklama": "description",
    "description": "description",
    "birim": "unit_price",
    "unit": "unit_price",
    "fiyat": "unit_price",
    "price": "unit_price",
    "toplam": "total_price",
    "total": "total_price",
}


def _parse_price(value: str | None) -> float | None:
    """Parse price string to float, handling Turkish/international formats."""
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,\-]", "", str(value).strip())
    if not cleaned:
        return None
    # Turkish format: 1.250,50 → 1250.50
    if "," in cleaned and "." in cleaned:
        if cleaned.index(",") > cleaned.index("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _match_header(cell: str | None) -> str | None:
    """Match a table header cell to a known column type."""
    if not cell:
        return None
    normalized = cell.strip().lower()
    # Direct match
    if normalized in _HEADER_ALIASES:
        return _HEADER_ALIASES[normalized]
    # Partial match
    for keyword, field in _HEADER_ALIASES.items():
        if keyword in normalized:
            return field
    return None


def _detect_column_mapping(header_row: list[str | None]) -> dict[int, str]:
    """Map column indices to field names based on header text."""
    mapping: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        field = _match_header(cell)
        if field and field not in mapping.values():
            mapping[idx] = field
    return mapping


def extract_parts_from_pdf(file_path: str) -> list[dict]:
    """Extract spare parts from PDF tables.

    Returns list of dicts with keys:
      honeywell_code, description, quantity, unit_price, total_price
    """
    parts: list[dict] = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # Find header row
                    col_mapping = {}
                    header_idx = 0
                    for row_idx, row in enumerate(table[:5]):
                        mapping = _detect_column_mapping(row)
                        if len(mapping) >= 2:
                            col_mapping = mapping
                            header_idx = row_idx
                            break

                    if not col_mapping:
                        continue

                    logger.info(
                        "PDF page %d: found table with %d columns mapped: %s",
                        page_num + 1, len(col_mapping), col_mapping,
                    )

                    # Extract data rows
                    for row in table[header_idx + 1:]:
                        if not row or all(not c for c in row):
                            continue

                        part = {
                            "honeywell_code": "",
                            "description": "",
                            "quantity": 1,
                            "unit_price": 0.0,
                            "total_price": 0.0,
                        }

                        for col_idx, field in col_mapping.items():
                            if col_idx >= len(row):
                                continue
                            cell = (row[col_idx] or "").strip()
                            if not cell:
                                continue

                            if field == "honeywell_code":
                                part["honeywell_code"] = cell
                            elif field == "description":
                                part["description"] = cell
                            elif field == "quantity":
                                try:
                                    part["quantity"] = int(re.sub(r"[^\d]", "", cell) or "1")
                                except ValueError:
                                    part["quantity"] = 1
                            elif field == "unit_price":
                                part["unit_price"] = _parse_price(cell) or 0.0
                            elif field == "total_price":
                                part["total_price"] = _parse_price(cell) or 0.0

                        # Skip rows without part code or description
                        if not part["honeywell_code"] and not part["description"]:
                            continue
                        # Skip header-like rows (e.g. "Toplam Fiyat:")
                        if part["honeywell_code"].lower() in ("toplam", "total", "-"):
                            continue

                        parts.append(part)

    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc)
        raise ValueError(f"PDF dosyasi okunamadi: {exc}")

    logger.info("Extracted %d parts from PDF: %s", len(parts), file_path)
    return parts


def extract_quote_data_from_pdf(file_path: str) -> dict:
    """Extract quote metadata + parts from a Honeywell-format PDF.

    Returns dict with customer info, items, and totals.
    """
    parts = extract_parts_from_pdf(file_path)

    # Extract text for customer info
    customer_name = ""
    customer_company = ""
    customer_address = ""
    customer_phone = ""
    customer_email = ""
    quote_number = ""
    currency = "USD"

    try:
        with pdfplumber.open(file_path) as pdf:
            if pdf.pages:
                text = pdf.pages[0].extract_text() or ""
                lines = text.split("\n")

                for line in lines:
                    line_lower = line.lower().strip()
                    # Customer name
                    if "müşteri adı:" in line_lower or "musteri adi:" in line_lower:
                        customer_name = line.split(":", 1)[-1].strip()
                    # Customer address
                    elif "müşteri adresi:" in line_lower or "musteri adresi:" in line_lower:
                        customer_address = line.split(":", 1)[-1].strip()
                    # Phone
                    elif "telefon" in line_lower and ":" in line:
                        customer_phone = line.split(":", 1)[-1].strip()
                    # Email
                    elif "e-posta:" in line_lower or "email:" in line_lower:
                        val = line.split(":", 1)[-1].strip()
                        if "@" in val:
                            customer_email = val
                    # Quote number
                    elif "teklif no:" in line_lower or "quote no:" in line_lower:
                        quote_number = line.split(":", 1)[-1].strip()
                    # Currency detection
                    if "USD" in line:
                        currency = "USD"
                    elif "EUR" in line:
                        currency = "EUR"
                    elif "TRY" in line or "TL" in line:
                        currency = "TRY"

    except Exception as exc:
        logger.warning("Failed to extract quote metadata from PDF: %s", exc)

    # Split customer_name if it contains company (e.g. "Onur - Demirören")
    if " - " in customer_name:
        name_parts = customer_name.split(" - ", 1)
        customer_name = name_parts[0].strip()
        customer_company = name_parts[1].strip()

    return {
        "customer_name": customer_name,
        "customer_company": customer_company,
        "customer_address": customer_address,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "quote_number": quote_number,
        "currency": currency,
        "items": [
            {
                "honeywell_code": p["honeywell_code"],
                "description": p["description"],
                "quantity": p["quantity"],
                "unit_price": p["unit_price"],
                "discount_pct": 0.0,
            }
            for p in parts
        ],
    }
