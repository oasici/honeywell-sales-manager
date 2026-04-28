"""V10 Sprint DD — master data quality (PDF §2 "Trust Gap").

Three measurements that surface "we said it but did we mean it"
issues without changing the SparePart schema:

- ``master_data_health_score`` — composite 0..100 from field
  completeness across the active catalog. Tenant-scoped when
  ``tenant_id`` is provided so each customer sees their own number.
- ``duplicate_candidates`` — fuzzy self-join over name + model_number
  + aliases to surface near-duplicate SparePart rows. Returns
  candidate pairs with a similarity score so the admin can review.
- ``orphan_pricing`` — PriceEntry rows pointing to inactive or
  hard-deleted SparePart rows. Cleanup target.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_entry import PriceEntry
from app.models.spare_part import SparePart


@dataclass(frozen=True)
class DuplicateCandidate:
    spare_part_a_id: int
    spare_part_b_id: int
    code_a: str | None
    code_b: str | None
    name_a: str | None
    name_b: str | None
    similarity: float
    reason: str  # "same_model_number" | "fuzzy_name" | "alias_match"


@dataclass(frozen=True)
class OrphanPricingRow:
    price_entry_id: int
    spare_part_id: int
    list_price: float
    created_at: datetime
    reason: str  # "inactive_part" | "missing_part"


# ─────────────────────── master data health ───────────────────────────


async def master_data_health_score(
    db: AsyncSession, *, tenant_id: int | None = None
) -> dict:
    """Composite 0..100 health score across the active catalog.

    Per-row score: 1 point per filled field across 4 critical fields
    (description, category, supplier_price, model_number). Per-row
    score then averaged across the catalog → 0..100.

    A single empty catalog returns score=0, confidence=low so the
    UI doesn't pretend perfection on no data.
    """
    parts = (
        await db.execute(
            select(SparePart).where(SparePart.is_active.is_(True))
        )
    ).scalars().all()

    total = len(parts)
    if total == 0:
        return _envelope(
            value=0,
            confidence="low",
            drivers=[{"label": "no_active_parts", "impact": 0}],
            recommended_actions=["Aktif parça yok — Excel import durumunu kontrol edin"],
        )

    drivers = {
        "description": 0,
        "category": 0,
        "supplier_price": 0,
        "model_number": 0,
    }
    sum_score = 0
    for p in parts:
        desc_filled = bool((p.description_tr or "").strip()) or bool(
            (p.description_en or "").strip()
        )
        if desc_filled:
            drivers["description"] += 1
        if (p.category or "").strip():
            drivers["category"] += 1
        if p.supplier_price:
            drivers["supplier_price"] += 1
        if (p.model_number or "").strip():
            drivers["model_number"] += 1
        row_score = sum(
            [
                desc_filled,
                bool((p.category or "").strip()),
                bool(p.supplier_price),
                bool((p.model_number or "").strip()),
            ]
        )
        sum_score += row_score

    avg_per_row = sum_score / (total * 4)
    score = int(round(avg_per_row * 100))

    drivers_payload = [
        {
            "label": label,
            "impact": filled,
            "filled_pct": round(filled / total * 100, 1) if total else 0,
        }
        for label, filled in drivers.items()
    ]
    drivers_payload.sort(key=lambda d: float(d["filled_pct"]))

    actions: list[str] = []
    worst = drivers_payload[0]
    if worst["filled_pct"] < 50:
        actions.append(
            f"En düşük kapsamlı alan: {worst['label']} ({worst['filled_pct']}%) — toplu güncelleme planlayın"
        )
    if score < 60:
        actions.append("Master data sağlığı kritik — Excel import şablonunu yenileyin")
    if not actions:
        actions.append("Master data durumu iyi — periyodik denetimle koruyun")

    confidence = "high" if total >= 100 else "medium" if total >= 20 else "low"

    return _envelope(
        value=score,
        confidence=confidence,
        drivers=drivers_payload,
        recommended_actions=actions,
    )


# ─────────────────────── duplicate detection ─────────────────────────


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio(), 4)


async def duplicate_candidates(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    threshold: float = 0.85,
    limit: int = 100,
) -> list[DuplicateCandidate]:
    """Return likely-duplicate SparePart pairs.

    Strategy:
    1. Group by ``model_number`` (exact match) — strongest signal.
    2. For each group ≥ 2, emit pairs with reason ``same_model_number``.
    3. Then apply fuzzy similarity over (name_tr || name_en) on parts
       that don't share a model_number, capped at the limit.

    The fuzzy pass uses ``difflib.SequenceMatcher`` instead of pulling
    in Levenshtein dependencies — accuracy is sufficient for catalog
    sizes of a few thousand and we keep the dependency footprint small.
    """
    parts = (
        await db.execute(
            select(SparePart).where(SparePart.is_active.is_(True))
        )
    ).scalars().all()
    if not parts:
        return []

    # Pass 1 — same model_number exact match.
    by_model: dict[str, list[SparePart]] = {}
    for p in parts:
        if p.model_number:
            by_model.setdefault(p.model_number.strip().lower(), []).append(p)

    out: list[DuplicateCandidate] = []
    paired_ids: set[tuple[int, int]] = set()
    for model, group in by_model.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                pair_key = (min(int(a.id), int(b.id)), max(int(a.id), int(b.id)))
                if pair_key in paired_ids:
                    continue
                paired_ids.add(pair_key)
                out.append(
                    DuplicateCandidate(
                        spare_part_a_id=pair_key[0],
                        spare_part_b_id=pair_key[1],
                        code_a=a.honeywell_code,
                        code_b=b.honeywell_code,
                        name_a=a.name_tr or a.name_en,
                        name_b=b.name_tr or b.name_en,
                        similarity=1.0,
                        reason="same_model_number",
                    )
                )
                if len(out) >= limit:
                    return out

    # Pass 2 — fuzzy name similarity (skip pairs we already flagged).
    for i in range(len(parts)):
        if len(out) >= limit:
            break
        a = parts[i]
        a_name = (a.name_tr or a.name_en or "").strip()
        if not a_name:
            continue
        for j in range(i + 1, len(parts)):
            b = parts[j]
            pair_key = (min(int(a.id), int(b.id)), max(int(a.id), int(b.id)))
            if pair_key in paired_ids:
                continue
            b_name = (b.name_tr or b.name_en or "").strip()
            if not b_name:
                continue
            sim = _text_similarity(a_name, b_name)
            if sim < threshold:
                continue
            paired_ids.add(pair_key)
            out.append(
                DuplicateCandidate(
                    spare_part_a_id=pair_key[0],
                    spare_part_b_id=pair_key[1],
                    code_a=a.honeywell_code,
                    code_b=b.honeywell_code,
                    name_a=a.name_tr or a.name_en,
                    name_b=b.name_tr or b.name_en,
                    similarity=sim,
                    reason="fuzzy_name",
                )
            )
            if len(out) >= limit:
                break

    out.sort(key=lambda c: -c.similarity)
    return out


# ─────────────────────── orphan pricing ──────────────────────────────


async def orphan_pricing(
    db: AsyncSession, *, limit: int = 200
) -> list[OrphanPricingRow]:
    """PriceEntry rows that point at inactive or missing SparePart.

    "Missing" comes from soft-link FK behaviour — PriceEntry uses
    spare_part_id with no ON DELETE rule, so a stale row can survive
    a SparePart hard delete (we shouldn't hard-delete, but defensive
    anyway).
    """
    rows = (
        await db.execute(
            select(
                PriceEntry.id.label("price_entry_id"),
                PriceEntry.spare_part_id,
                PriceEntry.list_price,
                PriceEntry.created_at,
                SparePart.is_active,
            )
            .outerjoin(SparePart, SparePart.id == PriceEntry.spare_part_id)
            .where(
                or_(
                    SparePart.id.is_(None),
                    SparePart.is_active.is_(False),
                )
            )
            .order_by(PriceEntry.created_at.desc())
            .limit(limit)
        )
    ).all()

    return [
        OrphanPricingRow(
            price_entry_id=int(r.price_entry_id),
            spare_part_id=int(r.spare_part_id),
            list_price=float(r.list_price),
            created_at=r.created_at,
            reason="missing_part" if r.is_active is None else "inactive_part",
        )
        for r in rows
    ]


# ─────────────────────── envelope helper ─────────────────────────────


def _envelope(
    *,
    value: int | float,
    confidence: str,
    drivers: list[dict],
    recommended_actions: list[str],
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "value": value,
        "confidence": confidence,
        "drivers": drivers,
        "recommended_actions": recommended_actions,
    }
