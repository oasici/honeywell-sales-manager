"""Lead lifecycle service — scoring, qualification, and conversion to Customer + Opportunity."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.lead import Lead

logger = logging.getLogger(__name__)

INACTIVITY_THRESHOLD_DAYS = 30
INACTIVITY_PENALTY_POINTS = 10

SCORING_CACHE_TTL_SECONDS = 300

# Module-level cache for scoring config
_scoring_config_cache: dict | None = None
_scoring_config_cached_at: float = 0


class LeadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_lead(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None = None,
        company: str | None = None,
        title: str | None = None,
        source: str = "manual",
        owner_id: int,
        notes: str | None = None,
        tenant_id: int | None = None,
    ) -> Lead:
        """Create a new lead and auto-score."""
        # Check duplicate
        existing = await self.db.execute(
            select(Lead).where(Lead.email == email)
        )
        if existing.scalar_one_or_none():
            raise BadRequestException(f"Bu email ile kayitli lead zaten var: {email}")

        lead = Lead(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            company=company,
            title=title,
            source=source,
            owner_id=owner_id,
            notes=notes,
            # V12 multi-tenant: caller passes the requesting user's tenant.
            tenant_id=tenant_id,
        )
        self.db.add(lead)
        await self.db.flush()
        await self.db.refresh(lead)

        # Auto-score
        lead.lead_score, _ = await self._compute_score(lead)

        # Auto-assign based on assignment rules
        assigned_owner = await self._evaluate_assignment_rules(lead)
        if assigned_owner:
            lead.owner_id = assigned_owner

        await self.db.flush()

        return lead

    async def update_lead(self, lead_id: int, **updates) -> Lead:
        """Update lead fields and re-score."""
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise NotFoundException("Lead bulunamadi")

        if lead.status == "converted":
            raise BadRequestException("Donusturulmus lead guncellenemez")

        for field, value in updates.items():
            if hasattr(lead, field) and value is not None:
                setattr(lead, field, value)

        lead.lead_score, _ = await self._compute_score(lead)
        await self.db.flush()
        await self.db.refresh(lead)
        return lead

    async def convert_lead(
        self,
        lead_id: int,
        user_id: int,
        create_opportunity: bool = False,
        opportunity_title: str | None = None,
        opportunity_amount: float | None = None,
    ) -> dict:
        """Convert a qualified lead to Customer + optional Opportunity.

        Returns dict with customer_id and opportunity_id.
        """
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise NotFoundException("Lead bulunamadi")

        if lead.status == "converted":
            raise BadRequestException("Bu lead zaten donusturulmus")

        if lead.status not in ("qualified", "contacted"):
            raise BadRequestException(
                f"Sadece 'qualified' veya 'contacted' lead donusturulebilir (mevcut: {lead.status})"
            )

        # Find or create customer
        cust_result = await self.db.execute(
            select(Customer).where(Customer.email == lead.email)
        )
        customer = cust_result.scalar_one_or_none()

        if not customer:
            customer = Customer(
                name=f"{lead.first_name} {lead.last_name}",
                company=lead.company or "",
                email=lead.email,
                phone=lead.phone or "",
                created_by=user_id,
            )
            self.db.add(customer)
            await self.db.flush()

        # Optionally create opportunity
        opportunity = None
        if create_opportunity:
            opp_title = opportunity_title or f"{lead.company or lead.last_name} - Yeni Firsat"
            opportunity = Opportunity(
                title=opp_title,
                stage="prospecting",
                amount=opportunity_amount,
                currency="TRY",
                customer_id=customer.id,
                owner_id=user_id,
            )
            self.db.add(opportunity)
            await self.db.flush()

        # Update lead
        lead.status = "converted"
        lead.converted_customer_id = customer.id
        lead.converted_opportunity_id = opportunity.id if opportunity else None
        lead.converted_at = datetime.now(timezone.utc)
        lead.converted_by = user_id
        await self.db.flush()

        # Activity log
        from app.services.activity_logger import log_activity
        await log_activity(
            self.db,
            activity_type="stage_change",
            entity_type="lead",
            entity_id=lead.id,
            customer_id=customer.id,
            opportunity_id=opportunity.id if opportunity else None,
            user_id=user_id,
            summary=f"Lead donusturuldu: {lead.first_name} {lead.last_name} → Musteri #{customer.id}",
        )

        return {
            "lead_id": lead.id,
            "customer_id": customer.id,
            "opportunity_id": opportunity.id if opportunity else None,
        }

    async def _evaluate_assignment_rules(self, lead: Lead) -> int | None:
        """Load active assignment rules and evaluate against lead. Returns user_id or None."""
        from app.models.lead_assignment_rule import LeadAssignmentRule
        from app.models.user import User

        result = await self.db.execute(
            select(LeadAssignmentRule)
            .where(LeadAssignmentRule.is_active.is_(True))
            .order_by(LeadAssignmentRule.priority.desc())
        )
        rules = result.scalars().all()

        for rule in rules:
            if not self._criteria_matches(rule, lead):
                continue

            if rule.assign_mode == "specific_user" and rule.assign_to_user_id:
                return rule.assign_to_user_id

            if rule.assign_mode == "round_robin":
                return await self._round_robin_assign()

            if rule.assign_mode == "least_loaded":
                return await self._least_loaded_assign()

        return None

    def _criteria_matches(self, rule, lead: Lead) -> bool:
        """Check if all criteria in rule match the lead."""
        import json

        try:
            criteria = json.loads(rule.criteria_json)
        except (json.JSONDecodeError, TypeError):
            return False

        if not isinstance(criteria, list):
            criteria = [criteria]

        for criterion in criteria:
            field = criterion.get("field", "")
            op = criterion.get("op", "")
            value = criterion.get("value", "")

            actual = getattr(lead, field, None)
            if actual is None:
                return False

            actual_str = str(actual).lower()
            value_str = str(value).lower()

            if op == "contains" and value_str not in actual_str:
                return False
            elif op == "eq" and actual_str != value_str:
                return False
            elif op == "starts_with" and not actual_str.startswith(value_str):
                return False
            elif op == "ends_with" and not actual_str.endswith(value_str):
                return False

        return True

    async def _round_robin_assign(self) -> int | None:
        """Assign to the next active user in round-robin order."""
        from app.models.user import User

        users_result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.id)
        )
        users = list(users_result.scalars().all())
        if not users:
            return None

        # Count leads per user to find the one with least recent assignment
        lead_counts = {}
        for user in users:
            count_result = await self.db.execute(
                select(func.count(Lead.id)).where(Lead.owner_id == user.id)
            )
            lead_counts[user.id] = count_result.scalar() or 0

        # Pick user with fewest leads (effectively round robin over time)
        min_count = min(lead_counts.values())
        for user in users:
            if lead_counts[user.id] == min_count:
                return user.id

        return users[0].id

    async def _least_loaded_assign(self) -> int | None:
        """Assign to the active user with fewest non-converted leads."""
        from app.models.user import User

        users_result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.id)
        )
        users = list(users_result.scalars().all())
        if not users:
            return None

        min_count = float("inf")
        best_user_id = users[0].id
        for user in users:
            count_result = await self.db.execute(
                select(func.count(Lead.id)).where(
                    Lead.owner_id == user.id,
                    Lead.status != "converted",
                )
            )
            count = count_result.scalar() or 0
            if count < min_count:
                min_count = count
                best_user_id = user.id

        return best_user_id

    async def _load_scoring_config(self) -> dict[str, int]:
        """Load scoring config from DB with 5-minute cache. Falls back to defaults."""
        global _scoring_config_cache, _scoring_config_cached_at

        now = time.time()
        if _scoring_config_cache is not None and (now - _scoring_config_cached_at) < SCORING_CACHE_TTL_SECONDS:
            return _scoring_config_cache

        from app.models.lead_scoring_config import LeadScoringConfig

        result = await self.db.execute(
            select(LeadScoringConfig).where(LeadScoringConfig.is_active.is_(True))
        )
        configs = result.scalars().all()

        if configs:
            config_map = {c.factor_name: c.weight for c in configs}
        else:
            # Hardcoded defaults when no DB config exists
            config_map = {
                "email": 10,
                "phone": 10,
                "company": 15,
                "title": 5,
                "external_domain": 10,
                "source_email": 20,
                "source_web": 15,
                "source_referral": 25,
                "source_manual": 5,
                "source_import": 10,
                "email_interactions": 5,
                "inactivity_decay": -INACTIVITY_PENALTY_POINTS,
            }

        _scoring_config_cache = config_map
        _scoring_config_cached_at = now
        return config_map

    async def _compute_score(self, lead: Lead) -> tuple[int, list[dict]]:
        """Rule-based lead scoring (0-100).

        Returns (score, breakdown) where breakdown is a list of factor dicts.
        Loads factor weights from DB config, falling back to hardcoded defaults.
        """
        weights = await self._load_scoring_config()
        score = 0
        breakdown: list[dict] = []

        # Basic info completeness
        if lead.email:
            points = weights.get("email", 10)
            score += points
            breakdown.append({"factor": "email", "points": points, "reason": "Email adresi mevcut"})
        if lead.phone:
            points = weights.get("phone", 10)
            score += points
            breakdown.append({"factor": "phone", "points": points, "reason": "Telefon numarasi mevcut"})
        if lead.company:
            points = weights.get("company", 15)
            score += points
            breakdown.append({"factor": "company", "points": points, "reason": "Sirket bilgisi mevcut"})
        if lead.title:
            points = weights.get("title", 5)
            score += points
            breakdown.append({"factor": "title", "points": points, "reason": "Unvan bilgisi mevcut"})

        # Known domain bonus
        if lead.email:
            domain = lead.email.split("@")[-1].lower() if "@" in lead.email else ""
            known_domains = settings.internal_domains_list
            if domain and domain not in known_domains:
                points = weights.get("external_domain", 10)
                score += points
                breakdown.append({
                    "factor": "external_domain",
                    "points": points,
                    "reason": f"Dis domain ({domain}) - potansiyel musteri",
                })

        # Source bonus (uses source_<type> keys from config)
        source_key = f"source_{lead.source}"
        default_source_scores = {
            "source_email": 20,
            "source_web": 15,
            "source_referral": 25,
            "source_manual": 5,
            "source_import": 10,
        }
        source_points = weights.get(source_key, default_source_scores.get(source_key, 0))
        if source_points:
            score += source_points
            breakdown.append({
                "factor": "source",
                "points": source_points,
                "reason": f"Kaynak: {lead.source}",
            })

        # Email interaction count
        from app.models.email_request import EmailRequest

        email_count_result = await self.db.execute(
            select(func.count(EmailRequest.id)).where(
                EmailRequest.from_address == lead.email
            )
        )
        email_count = email_count_result.scalar() or 0
        per_interaction = weights.get("email_interactions", 5)
        interaction_points = min(email_count * per_interaction, 25)
        if interaction_points:
            score += interaction_points
            breakdown.append({
                "factor": "email_interactions",
                "points": interaction_points,
                "reason": f"{email_count} email etkilesimi",
            })

        # Temporal decay: check last email interaction
        if lead.email:
            last_email_result = await self.db.execute(
                select(func.max(EmailRequest.received_at)).where(
                    EmailRequest.from_address == lead.email
                )
            )
            last_email_date = last_email_result.scalar()
            if last_email_date is not None:
                # Ensure timezone-aware (SQLite returns naive datetimes)
                if last_email_date.tzinfo is None:
                    last_email_date = last_email_date.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - last_email_date).days
                if days_since > INACTIVITY_THRESHOLD_DAYS:
                    penalty = abs(weights.get("inactivity_decay", INACTIVITY_PENALTY_POINTS))
                    score -= penalty
                    breakdown.append({
                        "factor": "inactivity_decay",
                        "points": -penalty,
                        "reason": f"{days_since} gunden fazla etkilesim yok",
                    })

        final_score = max(0, min(score, 100))
        return final_score, breakdown

    async def compute_score_breakdown(self, lead: Lead) -> list[dict]:
        """Compute and return only the score breakdown for a lead."""
        _, breakdown = await self._compute_score(lead)
        return breakdown

    async def rescore_all_leads(self) -> int:
        """Re-score all non-converted leads. Returns count."""
        result = await self.db.execute(
            select(Lead).where(Lead.status != "converted")
        )
        leads = list(result.scalars().all())

        count = 0
        for lead in leads:
            lead.lead_score, _ = await self._compute_score(lead)
            count += 1

        await self.db.flush()
        logger.info("Re-scored %d leads", count)
        return count

    async def auto_create_lead_from_email(
        self, from_address: str, subject: str | None = None, owner_id: int = 1
    ) -> Lead | None:
        """Create a lead from incoming email if sender is not a known customer or lead."""
        from app.models.customer import Customer

        # Skip if already a customer
        cust = await self.db.execute(
            select(Customer).where(Customer.email == from_address)
        )
        if cust.scalar_one_or_none():
            return None

        # Skip if already a lead
        existing = await self.db.execute(
            select(Lead).where(Lead.email == from_address)
        )
        if existing.scalar_one_or_none():
            return None

        # Extract name from email
        local_part = from_address.split("@")[0] if "@" in from_address else from_address
        parts = local_part.replace(".", " ").replace("_", " ").replace("-", " ").split()
        first_name = parts[0].capitalize() if parts else "Unknown"
        last_name = parts[1].capitalize() if len(parts) > 1 else ""

        try:
            lead = await self.create_lead(
                first_name=first_name,
                last_name=last_name or "(Bilinmiyor)",
                email=from_address,
                source="email",
                owner_id=owner_id,
                notes=f"Email'den otomatik olusturuldu: {subject or ''}",
            )
            logger.info("Auto-created lead from email: %s", from_address)
            return lead
        except BadRequestException:
            return None
