"""Sprint 4 — transcript katılımcılarından stakeholder zenginleştirmesi."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.user import User
from app.services.stakeholder_enrichment_service import parse_participant_tokens


def test_parse_participants_angle_brackets():
    raw = 'Ali Veli <ali@co.com>; "Jane Doe" <jane@x.org>, plain@mail.com'
    pairs = parse_participant_tokens(raw)
    names = {p[0].lower() for p in pairs}
    assert "ali veli" in names
    assert any(p[1] == "jane@x.org" for p in pairs)


@pytest.mark.asyncio
async def test_enrich_from_transcript_creates_rows(db: AsyncSession):
    from app.models.engagement import Transcript
    from app.services.stakeholder_enrichment_service import enrich_from_transcript

    u = User(
        email="se@test.com",
        full_name="SE",
        hashed_password=hash_password("x"),
        role="sales_rep",
        is_active=True,
    )
    db.add(u)
    await db.flush()
    await db.refresh(u)
    c = Customer(name="Acme", email="acme_se@test.com", company="Acme", created_by=u.id)
    db.add(c)
    await db.commit()
    await db.refresh(c)

    o = Opportunity(
        title="Deal",
        stage="qualified",
        status="active",
        owner_id=u.id,
        customer_id=c.id,
        amount=1.0,
        currency="TRY",
    )
    db.add(o)
    await db.commit()
    await db.refresh(o)

    t = Transcript(
        title="Call",
        content="x" * 50,
        opportunity_id=o.id,
        customer_id=None,
        source="paste",
        participants="Karar Verici <dm@buyer.com>, Etkileyici",
        created_by=u.id,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)

    ids = await enrich_from_transcript(db, t, u.id)
    await db.commit()
    assert len(ids) >= 1

    rows = (await db.execute(select(Stakeholder).where(Stakeholder.opportunity_id == o.id))).scalars().all()
    assert len(rows) >= 1
    assert any(s.is_auto_detected for s in rows)


@pytest.mark.asyncio
async def test_create_transcript_enriches_when_flag_on(client: AsyncClient, db: AsyncSession, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_BUYER_MAP", True)

    mgr = User(
        email="se_api@test.com",
        full_name="Mgr",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(mgr)
    await db.flush()
    await db.refresh(mgr)
    c = Customer(name="Co", email="co_se_api@test.com", company="Co", created_by=mgr.id)
    db.add(c)
    await db.commit()
    await db.refresh(c)

    o = Opportunity(
        title="O",
        stage="qualified",
        status="active",
        owner_id=mgr.id,
        customer_id=c.id,
        amount=10.0,
        currency="TRY",
    )
    db.add(o)
    await db.commit()
    await db.refresh(o)

    h = {"Authorization": f"Bearer {create_access_token({'sub': str(mgr.id)})}"}
    r = await client.post(
        "/api/v1/transcripts/",
        headers=h,
        json={
            "title": "Toplanti notu",
            "content": "a" * 40,
            "opportunity_id": o.id,
            "participants": "Patron <ceo@buyer.test>",
            "source": "paste",
        },
    )
    assert r.status_code == 201

    rows = (await db.execute(select(Stakeholder).where(Stakeholder.opportunity_id == o.id))).scalars().all()
    assert any(s.email == "ceo@buyer.test" for s in rows)
