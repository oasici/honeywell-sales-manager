"""v2 Engagement tests — transcripts, keyword packs, sequences, segments, coaching."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(email="eng_mgr@test.com", full_name="Eng Manager",
                hashed_password=hash_password("Test1234"), role="sales_manager", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_transcript_crud(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)

    r = await client.post("/api/v1/transcripts/", json={
        "title": "Kordsa gorusme", "content": "Merhaba, fiyat konusunda endiselerimiz var. Rakip firma daha uygun teklif verdi.",
    }, headers=h)
    assert r.status_code == 201
    assert "keywords_found" in r.json()

    r = await client.get("/api/v1/transcripts/", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_transcript_search(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    await client.post("/api/v1/transcripts/", json={
        "title": "Arama kaydı", "content": "Musteri fiyat indirimi istedi ve rakip alternatifleri dile getirdi.",
    }, headers=h)

    r = await client.get("/api/v1/transcripts/search?q=fiyat", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert "snippet" in r.json()["items"][0]


@pytest.mark.asyncio
async def test_keyword_pack_crud(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)

    r = await client.post("/api/v1/keyword-packs/", json={
        "name": "Fiyat Endisesi", "category": "pricing",
        "keywords": ["fiyat", "pahali", "indirim", "butce"],
    }, headers=h)
    assert r.status_code == 201

    r = await client.get("/api/v1/keyword-packs/", headers=h)
    assert r.status_code == 200
    assert len(r.json()["packs"]) >= 1


@pytest.mark.asyncio
async def test_sequence_crud_and_enroll(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)

    r = await client.post("/api/v1/sequences/", json={
        "name": "Yeni Musteri Takip",
        "steps": [
            {"step": 1, "action": "email", "delay_days": 0, "template": "Hosgeldiniz"},
            {"step": 2, "action": "task", "delay_days": 3, "template": "Takip araması yap"},
        ],
    }, headers=h)
    assert r.status_code == 201
    seq_id = r.json()["id"]

    r = await client.post("/api/v1/sequences/enroll", json={
        "sequence_id": seq_id,
    }, headers=h)
    assert r.status_code == 201
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_segment_crud(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)

    r = await client.post("/api/v1/segments/", json={
        "name": "Sanayi Firmalari",
        "rules": [{"field": "company", "op": "contains", "value": "sanayi"}],
    }, headers=h)
    assert r.status_code == 201
    seg_id = r.json()["id"]

    r = await client.get(f"/api/v1/segments/{seg_id}/customers", headers=h)
    assert r.status_code == 200
    assert "customers" in r.json()


@pytest.mark.asyncio
async def test_coaching_scorecards(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/coaching/scorecards?window=30", headers=h)
    assert r.status_code == 200
    assert "scorecards" in r.json()
