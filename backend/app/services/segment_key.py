"""Segment-key derivation used across V5 intelligence services.

The segment key is a stable identifier of the form
``{industry}_{size_band}_{amount_band}_{product_family}`` and is the
join key behind ``segment_benchmarks_daily``, ``dna_patterns``,
``objection_patterns``, and ``network_*`` tables.

Defaults
--------
- ``industry``: from ``customer.industry`` if present, else ``"unknown"``
- ``size_band``: from ``customer.employee_count`` bucketed (smb / mid /
  enterprise / unknown)
- ``amount_band``: from ``opportunity.amount`` bucketed in TRY
  (sub_50k / 50k_200k / 200k_1m / 1m_plus / unknown)
- ``product_family``: from ``opportunity.product_family`` if added
  later; today returns ``"general"``

Keep this file dependency-light — it's imported from anywhere we need
the identifier and we don't want a cycle through services.
"""

from __future__ import annotations

from typing import Optional


def _size_band(employee_count: Optional[int]) -> str:
    if employee_count is None or employee_count <= 0:
        return "unknown"
    if employee_count < 50:
        return "smb"
    if employee_count < 500:
        return "mid"
    return "enterprise"


def _amount_band(amount_try: Optional[float]) -> str:
    if amount_try is None or amount_try <= 0:
        return "unknown"
    if amount_try < 50_000:
        return "sub_50k"
    if amount_try < 200_000:
        return "50k_200k"
    if amount_try < 1_000_000:
        return "200k_1m"
    return "1m_plus"


def derive_segment_key(
    *,
    industry: Optional[str] = None,
    employee_count: Optional[int] = None,
    amount_try: Optional[float] = None,
    product_family: Optional[str] = None,
) -> str:
    """Build the canonical segment key. None-safe for every input."""
    parts = [
        (industry or "unknown").strip().lower().replace(" ", "_") or "unknown",
        _size_band(employee_count),
        _amount_band(amount_try),
        (product_family or "general").strip().lower().replace(" ", "_") or "general",
    ]
    return "_".join(parts)
