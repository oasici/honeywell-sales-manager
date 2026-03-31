"""Regex-based fallback parser for when Claude API is unavailable.

Extracts part codes, quantities, and customer names using pattern matching.
Returns partial results rather than empty data.
"""

import re

# Honeywell part number patterns
PART_CODE_PATTERNS = [
    re.compile(r"\b[A-Z]{1,3}\d{4}[A-Z]\d{4}\b"),          # CC1234X1234
    re.compile(r"\b\d{1,3}-\d{3}-\d{3}-\d{2}\b"),           # 0-000-134-01
    re.compile(r"\b\d{5,8}-\d{2,4}\b"),                      # 12345-12
    re.compile(r"\b[A-Z]{2,4}-[A-Z0-9]{2,10}\b"),            # EBI-R500, HW-GASD
    re.compile(r"\b[A-Z]{2}\d{4,6}\b"),                      # XX1234
    re.compile(r"\b[A-Z]\d{4}[A-Z]\d{4}\b"),                 # X1234X1234
    re.compile(r"\b\d{5}-\d{3}\b"),                           # 01004-001
]

QUANTITY_PATTERNS = [
    re.compile(r"(\d+)\s*(?:adet|pcs|pieces|parca|parça|qty)", re.IGNORECASE),
    re.compile(r"(?:qty|adet|miktar)[:\s]*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*(?:x|X)\s+[A-Z]"),
]

# Line-based part extraction: "1. CODE - Description - N adet"
LINE_PART_PATTERN = re.compile(
    r"^\s*\d+[\.\)]\s*([A-Z0-9][\w-]{2,20})\s*[-–]\s*(.+?)(?:\s*[-–]\s*(\d+)\s*(?:adet|pcs|qty))?\s*(?:\((\w+)\))?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

CUSTOMER_NAME_PATTERN = re.compile(
    r"(?:sayg[ıi]lar[ıi]mla|regards|best regards|thanks|tesekkurler"
    r"|saygılarımla)[,\s]*\n+([A-ZÇĞİÖŞÜa-zçğıöşü ]{3,40})",
    re.IGNORECASE,
)

MIN_BODY_LENGTH_FOR_API = 50


def pre_filter_email(body: str, subject: str) -> str:
    """Decide whether an email needs Claude API processing.

    Returns:
        "skip" - too short with no part codes, skip API call
        "likely_parts" - contains part number patterns
        "normal" - needs full API analysis
    """
    text = f"{subject} {body}".strip()

    if len(text) < MIN_BODY_LENGTH_FOR_API:
        has_part_codes = any(p.search(text) for p in PART_CODE_PATTERNS)
        if not has_part_codes:
            return "skip"

    if any(p.search(text) for p in PART_CODE_PATTERNS):
        return "likely_parts"

    return "normal"


def regex_fallback_parse(body: str, subject: str) -> dict:
    """Extract email data using regex when Claude API is unavailable.

    Extracts part codes, quantities, and customer name from text patterns.
    Returns partial results with low confidence scores.
    """
    text = f"{subject}\n{body}"
    parts = []
    seen_codes: set[str] = set()

    # Try line-based extraction first (more accurate)
    for match in LINE_PART_PATTERN.finditer(text):
        code = match.group(1).strip()
        desc = match.group(2).strip() if match.group(2) else ""
        qty = int(match.group(3)) if match.group(3) else 1
        urgency = match.group(4).lower() if match.group(4) else "normal"
        if urgency in ("acil", "critical", "urgent"):
            urgency = "critical"
        elif urgency in ("yuksek", "high"):
            urgency = "high"
        else:
            urgency = "normal"
        parts.append({
            "part_code": code,
            "part_description": desc or f"Part {code}",
            "quantity": qty,
            "urgency": urgency,
        })
        seen_codes.add(code)

    # Fall back to pattern-based extraction for codes not found by line parser
    found_codes = _extract_part_codes(text)
    quantities = _extract_quantities(text, found_codes)

    for code in found_codes:
        if code in seen_codes:
            continue
        parts.append({
            "part_code": code,
            "part_description": f"Part {code} (regex extraction)",
            "quantity": quantities.get(code, 1),
            "urgency": "normal",
        })

    customer_name = _extract_customer_name(body)
    is_spare_part = len(parts) > 0
    category = "spare_part_request" if is_spare_part else "general_inquiry"
    confidence = 0.4 if parts else 0.2

    return {
        "language": "tr",
        "customer_name": customer_name,
        "customer_company": "",
        "parts": parts,
        "is_spare_part_request": is_spare_part,
        "category": category,
        "confidence": confidence,
    }


def _extract_part_codes(text: str) -> list[str]:
    """Find all unique Honeywell part codes in text."""
    found: list[str] = []
    for pattern in PART_CODE_PATTERNS:
        found.extend(pattern.findall(text))
    return list(dict.fromkeys(found))


def _extract_quantities(text: str, codes: list[str]) -> dict[str, int]:
    """Extract quantities near each part code."""
    quantities: dict[str, int] = {}
    for code in codes:
        code_pos = text.find(code)
        context_start = max(0, code_pos - 30)
        context_end = code_pos + len(code) + 30
        surrounding = text[context_start:context_end]
        for qty_pattern in QUANTITY_PATTERNS:
            match = qty_pattern.search(surrounding)
            if match:
                quantities[code] = int(match.group(1))
                break
    return quantities


def _extract_customer_name(body: str) -> str:
    """Extract customer name from email signature."""
    match = CUSTOMER_NAME_PATTERN.search(body)
    if match:
        return match.group(1).strip()
    return ""
