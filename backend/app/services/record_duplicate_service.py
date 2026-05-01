"""Record duplicate detection and merge service.

Provides fuzzy matching to find potential duplicate customers/leads
and merge functionality to consolidate records.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.team import AccountTeam
from app.models.user import User
from app.services.tenant_context import assert_same_tenant

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.6
EMAIL_EXACT_MATCH_SCORE = 1.0
MAX_CANDIDATES = 200


def _similarity(a: str | None, b: str | None) -> float:
    """Compute similarity ratio between two strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class RecordDuplicateService:
    """Detects and merges duplicate customer/lead records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_duplicates(
        self,
        entity_type: str,
        name: str,
        company: str | None = None,
        email: str | None = None,
        exclude_id: int | None = None,
    ) -> list[dict]:
        """Find potential duplicates using fuzzy matching.

        Queries candidates via ILIKE, scores each with SequenceMatcher,
        and returns matches above the similarity threshold.
        """
        model = Customer if entity_type == "customer" else Lead
        name_field = model.name if entity_type == "customer" else None

        safe_name = name.replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{safe_name}%"

        if entity_type == "customer":
            conditions = [Customer.name.ilike(search_term)]
            if company:
                safe_company = company.replace("%", "\\%").replace("_", "\\_")
                conditions.append(Customer.company.ilike(f"%{safe_company}%"))
            query = select(Customer).where(or_(*conditions))
            if exclude_id:
                query = query.where(Customer.id != exclude_id)
            query = query.limit(MAX_CANDIDATES)
        else:
            first_part = safe_name.split()[0] if safe_name.split() else safe_name
            conditions = [
                Lead.first_name.ilike(f"%{first_part}%"),
                Lead.last_name.ilike(f"%{first_part}%"),
            ]
            if company:
                safe_company = company.replace("%", "\\%").replace("_", "\\_")
                conditions.append(Lead.company.ilike(f"%{safe_company}%"))
            query = select(Lead).where(or_(*conditions))
            if exclude_id:
                query = query.where(Lead.id != exclude_id)
            query = query.limit(MAX_CANDIDATES)

        result = await self.db.execute(query)
        candidates = result.scalars().all()

        matches = []
        for candidate in candidates:
            if entity_type == "customer":
                candidate_name = candidate.name or ""
                candidate_company = candidate.company
                candidate_email = candidate.email
            else:
                candidate_name = f"{candidate.first_name} {candidate.last_name}"
                candidate_company = candidate.company
                candidate_email = candidate.email

            # Check email exact match first
            if email and candidate_email and email.lower().strip() == candidate_email.lower().strip():
                matches.append({
                    "id": candidate.id,
                    "name": candidate_name,
                    "company": candidate_company or "",
                    "email": candidate_email,
                    "similarity": EMAIL_EXACT_MATCH_SCORE,
                })
                continue

            name_score = _similarity(name, candidate_name)
            company_score = _similarity(company, candidate_company) if company else 0.0

            # Weighted average: name matters more
            combined_score = name_score * 0.7 + company_score * 0.3 if company else name_score

            if combined_score >= SIMILARITY_THRESHOLD:
                matches.append({
                    "id": candidate.id,
                    "name": candidate_name,
                    "company": candidate_company or "",
                    "email": candidate_email or "",
                    "similarity": round(combined_score, 2),
                })

        matches.sort(key=lambda m: m["similarity"], reverse=True)
        return matches

    async def preview_merge(
        self,
        entity_type: str,
        winner_id: int,
        loser_id: int,
    ) -> dict:
        """Show side-by-side comparison and counts of related records."""
        if entity_type != "customer":
            return {"error": "Sadece musteri birlestirme desteklenmektedir"}

        winner_result = await self.db.execute(
            select(Customer).where(Customer.id == winner_id)
        )
        winner = winner_result.scalar_one_or_none()

        loser_result = await self.db.execute(
            select(Customer).where(Customer.id == loser_id)
        )
        loser = loser_result.scalar_one_or_none()

        if not winner or not loser:
            return {"error": "Kayit bulunamadi"}

        # Count related records for the loser
        quote_count = await self._count_related(Quote.customer_id, loser_id)
        opp_count = await self._count_related(Opportunity.customer_id, loser_id)
        email_count = await self._count_related(EmailRequest.customer_id, loser_id)
        activity_count = await self._count_related(ActivityLog.customer_id, loser_id)
        team_count = await self._count_related(AccountTeam.customer_id, loser_id)

        return {
            "winner": self._customer_to_dict(winner),
            "loser": self._customer_to_dict(loser),
            "related_counts": {
                "quotes": quote_count,
                "opportunities": opp_count,
                "emails": email_count,
                "activities": activity_count,
                "team_members": team_count,
            },
        }

    async def merge_records(
        self,
        entity_type: str,
        winner_id: int,
        loser_id: int,
        user_id: int,
        current_user: User | None = None,
    ) -> dict:
        """Merge loser into winner. Reassign all related records, then delete loser.

        ``current_user`` is required to enforce multi-tenant isolation
        (audit TEN-8). Optional only because legacy callers haven't
        been updated yet — when None, no tenant check runs and a
        warning is logged so the gap surfaces.
        """
        if entity_type != "customer":
            return {"error": "Sadece musteri birlestirme desteklenmektedir"}

        winner_result = await self.db.execute(
            select(Customer).where(Customer.id == winner_id)
        )
        winner = winner_result.scalar_one_or_none()

        loser_result = await self.db.execute(
            select(Customer).where(Customer.id == loser_id)
        )
        loser = loser_result.scalar_one_or_none()

        if not winner or not loser:
            return {"error": "Kayit bulunamadi"}

        # Cross-tenant guard (audit TEN-8). Both records must belong
        # to the caller's tenant — otherwise a manager could merge a
        # foreign tenant's customer into one of their own.
        if current_user is not None:
            assert_same_tenant(
                winner, current_user, exception_cls=NotFoundException,
            )
            assert_same_tenant(
                loser, current_user, exception_cls=NotFoundException,
            )
        else:
            logger.warning(
                "merge_records called without current_user — tenant check skipped"
            )

        reassigned = {}

        # Reassign quotes
        result = await self.db.execute(
            update(Quote)
            .where(Quote.customer_id == loser_id)
            .values(customer_id=winner_id)
        )
        reassigned["quotes"] = result.rowcount

        # Reassign opportunities
        result = await self.db.execute(
            update(Opportunity)
            .where(Opportunity.customer_id == loser_id)
            .values(customer_id=winner_id)
        )
        reassigned["opportunities"] = result.rowcount

        # Reassign email requests
        result = await self.db.execute(
            update(EmailRequest)
            .where(EmailRequest.customer_id == loser_id)
            .values(customer_id=winner_id)
        )
        reassigned["emails"] = result.rowcount

        # Reassign activity logs
        result = await self.db.execute(
            update(ActivityLog)
            .where(ActivityLog.customer_id == loser_id)
            .values(customer_id=winner_id)
        )
        reassigned["activities"] = result.rowcount

        # Remove duplicate team members, then reassign remaining
        await self.db.execute(
            delete(AccountTeam).where(
                AccountTeam.customer_id == loser_id,
                AccountTeam.user_id.in_(
                    select(AccountTeam.user_id).where(
                        AccountTeam.customer_id == winner_id
                    )
                ),
            )
        )
        result = await self.db.execute(
            update(AccountTeam)
            .where(AccountTeam.customer_id == loser_id)
            .values(customer_id=winner_id)
        )
        reassigned["team_members"] = result.rowcount

        # Delete the loser record
        await self.db.execute(
            delete(Customer).where(Customer.id == loser_id)
        )

        # Create audit log entry
        audit_entry = ActivityLog(
            activity_type="merge_customer",
            entity_type="customer",
            entity_id=winner_id,
            user_id=user_id,
            customer_id=winner_id,
            summary=f"Musteri #{loser_id} bu kayitla birlestirildi. Aktarilan: {reassigned}",
        )
        self.db.add(audit_entry)

        await self.db.commit()

        logger.info(
            "Customer %d merged into %d by user %d. Reassigned: %s",
            loser_id, winner_id, user_id, reassigned,
        )

        return {
            "message": f"Musteri #{loser_id} basariyla #{winner_id} ile birlestirildi",
            "reassigned_counts": reassigned,
        }

    async def _count_related(self, column, record_id: int) -> int:
        """Count related records for a given foreign key column."""
        result = await self.db.execute(
            select(func.count()).where(column == record_id)
        )
        return result.scalar() or 0

    @staticmethod
    def _customer_to_dict(customer: Customer) -> dict:
        """Convert a Customer model to a dictionary."""
        return {
            "id": customer.id,
            "name": customer.name,
            "company": customer.company or "",
            "email": customer.email,
            "phone": customer.phone or "",
            "address": customer.address or "",
            "tax_id": customer.tax_id or "",
            "preferred_lang": customer.preferred_lang,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
        }
