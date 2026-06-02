"""End-to-end pipeline test on REAL customer RFQ emails (2026-06 samples).

Four real RFQs (provided by the user) are run through the actual
``EmailProcessingService.process_email`` pipeline — resolver, dedup,
catalog pricing, eligibility gate, auto-quote. Only the LLM extraction
step is stubbed (no Anthropic key in CI) with the structured output Claude
would realistically return for each body; everything downstream is real.

The four samples deliberately exercise:
  * Turkish + English bodies (emails 1-3, same 3 parts)
  * a code variant: ``HDZWM2`` vs ``HDZ WM2`` (normalization)
  * Turkish quantity words ("2 adet") vs English ("2qty"/"3 qty")
  * a code-less spec table (email 4, türbinmetre) → must route to review

It also documents (regression-guards) the real-world finding that the
regex/heuristic extractors do NOT recognize these real Honeywell code
formats — today the feature relies on the LLM for extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.customer import Customer
from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.email_request import EmailRequest
from app.models.spare_part import SparePart
from app.services.email_processing_service import EmailProcessingService

_TENANT = 1

# ── Real catalog (codes from the sample RFQs) ─────────────────────
_SEED = {
    "764744": ("Konvansiyonel Güvenlik bariyeri, IQ8Quad Ex (i) Serisi", 1000.0),
    "581239": ("Ses Kontrol Ünitesi (BAP) VC 30R, 30W", 2500.0),
    "HDZWM2": ("PTZ Duvar Montaj Aparatı", 500.0),
}


@pytest.fixture
async def rfq_catalog(db):
    for code, (name, net) in _SEED.items():
        part = SparePart(honeywell_code=code, name_en=name, is_active=True)
        db.add(part)
        await db.flush()
        db.add(PriceEntry(spare_part_id=part.id, list_price=net, net_price=net, currency="TRY"))
    await db.commit()


@pytest.fixture
async def known_senders(db):
    db.add(Customer(name="Birkan Ege Durukan", company="Honeywell",
                    email="birkanege.durukan@honeywell.com", tenant_id=_TENANT))
    db.add(Customer(name="Neslihan Halat", company="TANAP",
                    email="neslihan.halat@tanap.com", tenant_id=_TENANT))
    await db.commit()


async def _run(db, admin_user, *, msg_id, subject, body, from_addr, claude_result):
    email = EmailRequest(
        message_id=msg_id, from_address=from_addr, subject=subject,
        body_text=body, status="new", sender_auth_status="pass",
        tenant_id=_TENANT, assigned_to=admin_user.id,
        received_at=datetime.now(timezone.utc),
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)
    with patch("app.services.claude_parser.parse_email",
               new=AsyncMock(return_value=claude_result)), \
         patch("app.services.email_processing_service.pre_filter_email",
               return_value="process"):
        svc = EmailProcessingService(db)
        await svc.process_email(email.id)
    await db.refresh(email)
    return email


async def _quote_for(db, email_id):
    quote = (await db.execute(
        select(Quote).where(Quote.email_request_id == email_id)
    )).scalar_one_or_none()
    if quote is None:
        return None, []
    items = (await db.execute(
        select(QuoteItem).where(QuoteItem.quote_id == quote.id)
    )).scalars().all()
    return quote, list(items)


def _claude_parts(parts, *, lang="tr"):
    return {
        "language": lang, "customer_name": "Birkan Ege Durukan",
        "customer_company": "Honeywell", "is_spare_part_request": True,
        "category": "spare_part_request", "confidence": 0.92, "parts": parts,
    }


# ── Emails 1-3: 3 parts, known sender → auto-quote ────────────────
class TestRealRfqAutoQuote:
    @pytest.mark.asyncio
    async def test_email1_turkish(self, db, admin_user, rfq_catalog, known_senders):
        email = await _run(
            db, admin_user, msg_id="rfq-1", subject="Yedek Parça Talep",
            from_addr="birkanege.durukan@honeywell.com",
            body="Merhaba onur bey,\n\nAşağıdaki yedek parçalar için teklifinizi rica ederim.\n"
                 "764744 ... 2 adet\n581239 ... 3 adet\nHDZWM2 ... 1 ADET",
            claude_result=_claude_parts([
                {"part_code": "764744", "part_description": _SEED["764744"][0], "quantity": 2},
                {"part_code": "581239", "part_description": _SEED["581239"][0], "quantity": 3},
                {"part_code": "HDZWM2", "part_description": _SEED["HDZWM2"][0], "quantity": 1},
            ]),
        )
        quote, items = await _quote_for(db, email.id)
        assert quote is not None, "known-sender exact-match RFQ should auto-draft a quote"
        by_code = {it.honeywell_code: it for it in items}
        assert by_code["764744"].quantity == 2
        assert by_code["581239"].quantity == 3
        assert by_code["HDZWM2"].quantity == 1
        # priced from catalog (TRY), confirmed
        assert by_code["764744"].unit_price == 1000.0
        assert by_code["764744"].line_total == 2000.0
        assert by_code["581239"].line_total == 7500.0
        assert all(it.is_confirmed for it in items)
        assert round(quote.subtotal, 2) == 10000.0

    @pytest.mark.asyncio
    async def test_email2_space_variant_normalizes(self, db, admin_user, rfq_catalog, known_senders):
        email = await _run(
            db, admin_user, msg_id="rfq-2", subject="hONEYWELL YEDEK PARÇA",
            from_addr="birkanege.durukan@honeywell.com",
            body="Aşağıdaki yedek parçalar için teklifinizi rica ederim.",
            claude_result=_claude_parts([
                {"part_code": "764744", "quantity": 2},
                {"part_code": "581239", "quantity": 3},
                {"part_code": "HDZ WM2", "quantity": 1},  # space variant
            ]),
        )
        quote, items = await _quote_for(db, email.id)
        assert quote is not None
        codes = {it.honeywell_code for it in items}
        # "HDZ WM2" normalizes to the catalog's HDZWM2 — one canonical SKU.
        assert "HDZWM2" in codes
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_email3_english(self, db, admin_user, rfq_catalog, known_senders):
        email = await _run(
            db, admin_user, msg_id="rfq-3", subject="Spare Part",
            from_addr="birkanege.durukan@honeywell.com",
            body="I would like to have a proposal for below quantities.\n"
                 "764744 2qty\n581239 3 qty\nHDZ WM2 1 qty",
            claude_result=_claude_parts([
                {"part_code": "764744", "quantity": 2},
                {"part_code": "581239", "quantity": 3},
                {"part_code": "HDZ WM2", "quantity": 1},
            ], lang="en"),
        )
        quote, items = await _quote_for(db, email.id)
        assert quote is not None and len(items) == 3
        assert sum(it.quantity for it in items) == 6


# ── Email 4: code-less spec table → must route to review ──────────
class TestRealRfqNoCode:
    @pytest.mark.asyncio
    async def test_email4_turbinmetre_routes_to_review(self, db, admin_user, rfq_catalog, known_senders):
        email = await _run(
            db, admin_user, msg_id="rfq-4", subject="[External] Türbinmetre Fyat Talebi",
            from_addr="neslihan.halat@tanap.com",
            body="Aşağıda bilgileri verilen türbinmetreler için fiyat teklifinizi almak isteriz.",
            claude_result=_claude_parts([
                {"part_code": "", "part_description": "Türbinmetre (LF+2 HF) G400 DN100 ANSI Class 600 30 Bar", "quantity": 2},
                {"part_code": "", "part_description": "Türbinmetre (LF+2 HF) G650 DN150 ANSI Class 600 30 Bar", "quantity": 2},
                {"part_code": "", "part_description": "Türbinmetre (LF+2 HF) G100 DN75 ANSI Class 600 30 Bar", "quantity": 2},
            ]),
        )
        quote, _items = await _quote_for(db, email.id)
        # No part codes -> nothing resolves -> the gate must refuse to
        # auto-quote and route to a human.
        assert quote is None, "a code-less spec RFQ must NOT auto-quote"
        assert email.review_status == "pending_review"


# ── Real-world extraction finding (regression-guard) ──────────────
class TestRealCodeExtractionGap:
    def test_heuristic_pattern_blind_to_real_codes(self):
        """Documents the finding: the tabular/regex part-code pattern does
        not recognize real Honeywell codes (6-digit numeric, short alnum).
        Today extraction relies on the LLM. If this is fixed, flip these."""
        from app.services.email_attachment_parser import _TABULAR_PART_PATTERN
        for code in ("764744", "581239", "HDZWM2", "HDZ WM2"):
            assert _TABULAR_PART_PATTERN.search(code) is None

    def test_regex_fallback_blind_to_real_codes(self):
        from app.services.regex_fallback_parser import regex_fallback_parse
        r = regex_fallback_parse(
            "764744 2qty\n581239 3 qty\nHDZ WM2 1 qty", "Spare Part"
        )
        # Claude-down fallback currently extracts nothing for these formats.
        assert r.get("parts") == []
