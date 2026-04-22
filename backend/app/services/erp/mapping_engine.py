"""Field translation between ERP DTOs and HSS ORM objects.

The mapping engine is intentionally tiny: each entity has a default map that
can be overridden per ``ERPConnection`` via the ``config_json`` column (JSON
under the ``field_map`` key).

Example override for Logo that calls the tax field ``VKN_TCKN`` instead of
the default ``tax_number``::

    {
      "field_map": {
        "customer": {"tax_number": "VKN_TCKN", "phone": "TELEFON1"}
      }
    }

This helper is pure and synchronous so it can be unit-tested without the DB.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# ── Charset normalizer ───────────────────────────────────────────────────────

_TR_SINGLE_QUOTE = "\u2019"  # curly apostrophe produced by Word/Outlook


def normalize_turkish(value: str | None) -> str | None:
    """Normalize common Windows-1254 ↔ UTF-8 quirks produced by Logo exports.

    - Collapse curly apostrophes to ASCII.
    - Strip NBSP and zero-width space.
    - Collapse whitespace.
    """
    if value is None:
        return None
    cleaned = value.replace(_TR_SINGLE_QUOTE, "'")
    cleaned = cleaned.replace("\xa0", " ").replace("\u200b", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


# ── Default field maps (internal_field -> ERP_field) ─────────────────────────

DEFAULT_CUSTOMER_MAP: dict[str, str] = {
    "name": "name",
    "tax_number": "tax_number",
    "email": "email",
    "phone": "phone",
    "address": "address",
    "city": "city",
}

DEFAULT_PRODUCT_MAP: dict[str, str] = {
    "sku": "sku",
    "name": "name",
    "description": "description",
    "unit_price": "unit_price",
    "currency": "currency",
    "vat_rate": "vat_rate",
}


# ── Core helpers ─────────────────────────────────────────────────────────────

def _load_overrides(config_json: str | None, entity: str) -> dict[str, str]:
    if not config_json:
        return {}
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError:
        return {}
    return (config.get("field_map") or {}).get(entity) or {}


def to_internal_customer(
    erp_payload: dict[str, Any], *, config_json: str | None = None
) -> dict[str, Any]:
    """Translate an ERP customer payload into kwargs for ``Customer``."""
    overrides = _load_overrides(config_json, "customer")
    field_map = {**DEFAULT_CUSTOMER_MAP, **overrides}

    out: dict[str, Any] = {}
    for internal_key, erp_key in field_map.items():
        value = erp_payload.get(erp_key)
        if isinstance(value, str):
            value = normalize_turkish(value)
        out[internal_key] = value

    # Composition rules the adapter cannot express via a flat map.
    if not out.get("name") and erp_payload.get("company"):
        out["name"] = normalize_turkish(erp_payload["company"])

    return out


def to_internal_product(
    erp_payload: dict[str, Any], *, config_json: str | None = None
) -> dict[str, Any]:
    overrides = _load_overrides(config_json, "product")
    field_map = {**DEFAULT_PRODUCT_MAP, **overrides}

    out: dict[str, Any] = {}
    for internal_key, erp_key in field_map.items():
        value = erp_payload.get(erp_key)
        if isinstance(value, str):
            value = normalize_turkish(value)
        out[internal_key] = value

    return out


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Stable hash for cheap "did this record change" checks."""
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def diff_payloads(
    hss: dict[str, Any], erp: dict[str, Any], *, ignore: set[str] | None = None
) -> list[dict[str, Any]]:
    """Return a list of ``{field, hss, erp}`` rows for fields that differ."""
    ignore = ignore or {"updated_at", "created_at", "last_synced_at"}
    diffs: list[dict[str, Any]] = []
    keys = (set(hss) | set(erp)) - ignore
    for key in sorted(keys):
        if hss.get(key) != erp.get(key):
            diffs.append({"field": key, "hss": hss.get(key), "erp": erp.get(key)})
    return diffs
