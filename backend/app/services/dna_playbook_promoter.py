"""DNA → Playbook auto-promoter (V6).

Bridges the V5 DNA pattern miner (which produces ``DnaPattern`` rows
with sequence templates + lift) to the V5 playbook layer (``Playbook``
+ ``PlaybookStep``). Mined patterns above a quality threshold become
playbook drafts so reps can actually execute the wisdom we've mined.

The mapping from token → playbook step is rule-based for V6 (one row
per token); a future iteration can use an LLM to write Turkish-
language step descriptions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.playbook import Playbook
from app.models.v5_dna_patterns import DnaPattern
from app.models.v5_playbook import (
    PlaybookAdherence,
    PlaybookPerformance,
    PlaybookStep,
)
from app.services.sequence_tokenizer import (
    TOK_3PLUS_STAKEHOLDERS,
    TOK_BUYER_REPLY_FAST,
    TOK_DISCOUNT_LOW,
    TOK_DM_BEFORE_DISCOUNT,
    TOK_FOLLOWUP_AFTER_QUOTE,
    TOK_MEETING_BEFORE_QUOTE,
    TOK_QUOTE_REVISED_AFTER_OBJECTION,
    TOK_STAGE_PROGRESSED_FAST,
)

logger = logging.getLogger(__name__)


# ─────────────────────── token → playbook step ───────────────────────


@dataclass(frozen=True)
class _StepTemplate:
    trigger: dict
    action: dict
    expected_window_hours: int
    success_metric: str


_TOKEN_TO_STEP: dict[str, _StepTemplate] = {
    TOK_FOLLOWUP_AFTER_QUOTE: _StepTemplate(
        trigger={"event_type": "quote_sent"},
        action={"action_type": "followup", "template": "Quote sonrası 24h içinde follow-up call/email"},
        expected_window_hours=24,
        success_metric="followup_logged",
    ),
    TOK_MEETING_BEFORE_QUOTE: _StepTemplate(
        trigger={"stage_changed_to": "qualified"},
        action={"action_type": "meeting", "template": "Quote göndermeden önce discovery meeting'i tamamla"},
        expected_window_hours=72,
        success_metric="meeting_logged",
    ),
    TOK_DM_BEFORE_DISCOUNT: _StepTemplate(
        trigger={"event_type": "discount_proposed"},
        action={
            "action_type": "stakeholder_add",
            "template": "İskonto önermeden önce karar vericiyi onaya dahil et",
        },
        expected_window_hours=48,
        success_metric="decision_maker_present",
    ),
    TOK_3PLUS_STAKEHOLDERS: _StepTemplate(
        trigger={"stage_changed_to": "proposal"},
        action={
            "action_type": "stakeholder_expand",
            "template": "Proposal aşamasında ≥3 stakeholder'a ulaş",
        },
        expected_window_hours=120,
        success_metric="stakeholder_count_3",
    ),
    TOK_DISCOUNT_LOW: _StepTemplate(
        trigger={"event_type": "discount_proposed"},
        action={"action_type": "discount_cap", "template": "İskonto %15'i geçmeden ROI artifact'ı gönder"},
        expected_window_hours=24,
        success_metric="discount_under_15",
    ),
    TOK_BUYER_REPLY_FAST: _StepTemplate(
        trigger={"event_type": "email_sent"},
        action={"action_type": "nudge", "template": "Outbound sonrası 48h içinde reply yoksa nudge sequence'ı başlat"},
        expected_window_hours=48,
        success_metric="buyer_reply",
    ),
    TOK_QUOTE_REVISED_AFTER_OBJECTION: _StepTemplate(
        trigger={"event_type": "objection_logged"},
        action={"action_type": "quote_revise", "template": "Objection sonrası 7 gün içinde quote revize et"},
        expected_window_hours=168,
        success_metric="quote_revised",
    ),
    TOK_STAGE_PROGRESSED_FAST: _StepTemplate(
        trigger={"stage_changed_to": "any"},
        action={"action_type": "next_step", "template": "Stage geçişinin ardından 7 gün içinde next-step planla"},
        expected_window_hours=168,
        success_metric="next_step_scheduled",
    ),
}


# ─────────────────────── promoter ────────────────────────────────────


async def promote_top_patterns(
    db: AsyncSession,
    *,
    min_lift: float = 1.5,
    min_support: int = 10,
) -> int:
    """Promote qualifying ``DnaPattern`` rows to draft playbooks.

    Only mines patterns whose ``lift_vs_baseline ≥ min_lift`` AND
    ``support_count ≥ min_support`` qualify. Idempotent — promoting
    the same pattern twice updates the existing draft instead of
    duplicating it (matched by ``Playbook.name``).
    """
    candidates = (
        await db.execute(
            select(DnaPattern)
            .where(DnaPattern.lift_vs_baseline >= min_lift)
            .where(DnaPattern.support_count >= min_support)
            .order_by(DnaPattern.lift_vs_baseline.desc())
        )
    ).scalars().all()
    if not candidates:
        return 0

    written = 0
    for pattern in candidates:
        try:
            tokens = list(json.loads(pattern.sequence_template_json))
        except (json.JSONDecodeError, TypeError):
            continue

        steps = [_TOKEN_TO_STEP[t] for t in tokens if t in _TOKEN_TO_STEP]
        if not steps:
            continue

        playbook_name = f"DNA: {pattern.segment_key} — {pattern.pattern_name}"[:200]

        existing = (
            await db.execute(
                select(Playbook).where(Playbook.name == playbook_name)
            )
        ).scalar_one_or_none()
        steps_payload = [
            {
                "step": i + 1,
                **step.action,
                "delay_days": 0,
                "trigger": step.trigger,
                "expected_window_hours": step.expected_window_hours,
            }
            for i, step in enumerate(steps)
        ]

        if existing is None:
            playbook = Playbook(
                name=playbook_name,
                description=(
                    f"Auto-promoted from DNA pattern (lift {pattern.lift_vs_baseline:.2f}, "
                    f"support {pattern.support_count})"
                ),
                trigger_conditions_json=json.dumps(
                    [{"field": "segment_key", "op": "eq", "value": pattern.segment_key}]
                ),
                steps_json=json.dumps(steps_payload),
                category="dna_promoted",
                is_active=False,  # require manager review before activation
            )
            db.add(playbook)
            await db.flush()
            playbook_id = playbook.id
        else:
            existing.steps_json = json.dumps(steps_payload)
            existing.description = (
                f"Auto-promoted from DNA pattern (lift {pattern.lift_vs_baseline:.2f}, "
                f"support {pattern.support_count})"
            )
            playbook_id = existing.id

        # Replace materialised step rows.
        old_steps = (
            await db.execute(
                select(PlaybookStep).where(PlaybookStep.playbook_id == playbook_id)
            )
        ).scalars().all()
        for s in old_steps:
            await db.delete(s)
        await db.flush()

        for i, step in enumerate(steps):
            db.add(
                PlaybookStep(
                    playbook_id=playbook_id,
                    step_no=i + 1,
                    trigger_condition_json=json.dumps(step.trigger),
                    recommended_action_json=json.dumps(step.action),
                    expected_window_hours=step.expected_window_hours,
                    success_metric=step.success_metric,
                )
            )

        written += 1

    await db.flush()
    return written


# ─────────────────────── adherence + lift ────────────────────────────


async def compute_adherence(
    db: AsyncSession, *, playbook_id: int, window_days: int = 30
) -> PlaybookPerformance:
    """Refresh the adherence + lift snapshot for one playbook.

    - Adherence: completed_eligible_steps / eligible_steps
    - Lift: winrate(followers) − winrate(non_followers) where a
      "follower" is an opp with at least one ``PlaybookAdherence`` row
      for this playbook in the window.
    """
    period_end = date.today()
    period_start = period_end - timedelta(days=window_days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    eligible_count = (
        await db.execute(
            select(func.count(PlaybookAdherence.id))
            .where(PlaybookAdherence.playbook_id == playbook_id)
            .where(PlaybookAdherence.eligible_at >= cutoff)
        )
    ).scalar() or 0
    completed_count = (
        await db.execute(
            select(func.count(PlaybookAdherence.id))
            .where(PlaybookAdherence.playbook_id == playbook_id)
            .where(PlaybookAdherence.eligible_at >= cutoff)
            .where(PlaybookAdherence.completed_at.isnot(None))
        )
    ).scalar() or 0
    completion_rate = (
        round(completed_count / eligible_count, 3) if eligible_count else 0.0
    )

    follower_opp_ids = (
        await db.execute(
            select(PlaybookAdherence.opportunity_id)
            .where(PlaybookAdherence.playbook_id == playbook_id)
            .where(PlaybookAdherence.eligible_at >= cutoff)
            .distinct()
        )
    ).scalars().all()

    follower_won = 0
    follower_total = 0
    if follower_opp_ids:
        ids = [int(x) for x in follower_opp_ids]
        follower_total = (
            await db.execute(
                select(func.count(Opportunity.id)).where(Opportunity.id.in_(ids))
            )
        ).scalar() or 0
        follower_won = (
            await db.execute(
                select(func.count(Opportunity.id))
                .where(Opportunity.id.in_(ids))
                .where(Opportunity.stage == "closed_won")
            )
        ).scalar() or 0

    non_follower_total = (
        await db.execute(
            select(func.count(Opportunity.id))
            .where(Opportunity.stage.in_(["closed_won", "closed_lost"]))
            .where(Opportunity.created_at >= cutoff)
        )
    ).scalar() or 0
    non_follower_won = (
        await db.execute(
            select(func.count(Opportunity.id))
            .where(Opportunity.stage == "closed_won")
            .where(Opportunity.created_at >= cutoff)
        )
    ).scalar() or 0
    if follower_opp_ids:
        non_follower_total = max(0, non_follower_total - follower_total)
        non_follower_won = max(0, non_follower_won - follower_won)

    follower_winrate = (follower_won / follower_total) if follower_total else 0.0
    non_follower_winrate = (
        non_follower_won / non_follower_total if non_follower_total else 0.0
    )
    lift = round(follower_winrate - non_follower_winrate, 3)

    existing = (
        await db.execute(
            select(PlaybookPerformance)
            .where(PlaybookPerformance.playbook_id == playbook_id)
            .where(PlaybookPerformance.period_start == period_start)
            .where(PlaybookPerformance.period_end == period_end)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = PlaybookPerformance(
            playbook_id=playbook_id,
            period_start=period_start,
            period_end=period_end,
            usage_count=eligible_count,
            completion_rate=completion_rate,
            won_rate=round(follower_winrate, 3),
            lift_vs_control=lift,
            sample_size=follower_total,
        )
        db.add(existing)
    else:
        existing.usage_count = eligible_count
        existing.completion_rate = completion_rate
        existing.won_rate = round(follower_winrate, 3)
        existing.lift_vs_control = lift
        existing.sample_size = follower_total
        existing.generated_at = datetime.now(timezone.utc)

    await db.flush()
    return existing
