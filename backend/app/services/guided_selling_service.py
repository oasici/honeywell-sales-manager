"""Guided selling / CPQ wizard evaluation service."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_bundle import ProductBundle
from app.models.selling_guide import SellingGuide
from app.models.spare_part import SparePart


class GuidedSellingService:
    """Evaluate guided-selling wizard answers and return suggested products."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_guides(self) -> list[dict]:
        result = await self.db.execute(
            select(SellingGuide)
            .where(SellingGuide.is_active.is_(True))
            .order_by(SellingGuide.name),
        )
        guides = result.scalars().all()
        return [self._serialize(g) for g in guides]

    async def get_guide(self, guide_id: int) -> dict | None:
        guide = await self.db.get(SellingGuide, guide_id)
        if not guide:
            return None
        return self._serialize(guide)

    async def create_guide(self, data: dict) -> SellingGuide:
        # Round-10 R10-DB-4 — tenant_id NOT NULL. Caller must pass it
        # (looked up from the creating user's tenant at the API layer).
        guide = SellingGuide(
            tenant_id=data["tenant_id"],
            name=data["name"],
            description=data.get("description"),
            steps_json=json.dumps(data.get("steps", []), ensure_ascii=False),
            product_rules_json=json.dumps(data.get("product_rules", []), ensure_ascii=False),
            is_active=data.get("is_active", True),
            created_by=data.get("created_by"),
        )
        self.db.add(guide)
        await self.db.flush()
        await self.db.refresh(guide)
        return guide

    async def evaluate_step(self, guide_id: int, answers: dict) -> dict:
        """Given answers so far, return suggested products."""
        guide = await self.db.get(SellingGuide, guide_id)
        if not guide:
            return {"suggested_parts": [], "suggested_bundles": [], "match_count": 0}

        rules = json.loads(guide.product_rules_json or "[]")

        suggested_part_ids: set[int] = set()
        suggested_bundle_ids: set[int] = set()

        for rule in rules:
            conditions = rule.get("conditions", {})
            is_match = all(answers.get(k) == v for k, v in conditions.items())
            if is_match:
                suggested_part_ids.update(rule.get("suggest_parts", []))
                suggested_bundle_ids.update(rule.get("suggest_bundles", []))

        parts = await self._load_parts(list(suggested_part_ids))
        bundles = await self._load_bundles(list(suggested_bundle_ids))

        return {
            "suggested_parts": parts,
            "suggested_bundles": bundles,
            "match_count": len(suggested_part_ids) + len(suggested_bundle_ids),
        }

    async def _load_parts(self, part_ids: list[int]) -> list[dict]:
        if not part_ids:
            return []
        result = await self.db.execute(
            select(SparePart).where(SparePart.id.in_(part_ids)),
        )
        return [
            {
                "id": p.id,
                "honeywell_code": p.honeywell_code,
                "name": p.name_tr or p.name_en,
                "unit_price": p.supplier_price or p.transfer_price or 0,
            }
            for p in result.scalars().all()
        ]

    async def _load_bundles(self, bundle_ids: list[int]) -> list[dict]:
        if not bundle_ids:
            return []
        result = await self.db.execute(
            select(ProductBundle).where(ProductBundle.id.in_(bundle_ids)),
        )
        return [
            {
                "id": b.id,
                "name": b.name,
                "description": b.description,
                "bundle_price": b.bundle_price,
            }
            for b in result.scalars().all()
        ]

    @staticmethod
    def _serialize(guide: SellingGuide) -> dict:
        return {
            "id": guide.id,
            "name": guide.name,
            "description": guide.description,
            "steps": json.loads(guide.steps_json or "[]"),
            "product_rules": json.loads(guide.product_rules_json or "[]"),
            "is_active": guide.is_active,
            "created_by": guide.created_by,
            "created_at": guide.created_at.isoformat() if guide.created_at else None,
        }
