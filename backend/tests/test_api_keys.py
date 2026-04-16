"""Tests for API key generation, validation, and revocation."""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import generate_api_key, validate_api_key
from app.models.api_key import ApiKey


class TestGenerateApiKey:
    """generate_api_key returns a valid plain key and matching hash."""

    def test_generates_prefixed_key(self):
        plain, key_hash = generate_api_key()
        assert plain.startswith("hsm_")
        assert len(plain) > 10

    def test_hash_matches_plain(self):
        plain, key_hash = generate_api_key()
        expected_hash = hashlib.sha256(plain.encode()).hexdigest()
        assert key_hash == expected_hash

    def test_generates_unique_keys(self):
        keys = {generate_api_key()[0] for _ in range(10)}
        assert len(keys) == 10


class TestApiKeyModel:
    """ApiKey model database operations."""

    @pytest.mark.asyncio
    async def test_create_api_key(self, db: AsyncSession):
        plain, key_hash = generate_api_key()

        api_key = ApiKey(
            key_hash=key_hash,
            name="Test Entegrasyon",
            user_id=1,
            scopes_json='["read:quotes"]',
        )
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        assert api_key.id is not None
        assert api_key.is_active is True
        assert api_key.rate_limit == 1000

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, db: AsyncSession):
        _, key_hash = generate_api_key()

        api_key = ApiKey(
            key_hash=key_hash,
            name="Silinecek Anahtar",
            user_id=1,
        )
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        api_key.is_active = False
        await db.commit()
        await db.refresh(api_key)

        assert api_key.is_active is False

    @pytest.mark.asyncio
    async def test_unique_key_hash_constraint(self, db: AsyncSession):
        _, key_hash = generate_api_key()

        key1 = ApiKey(key_hash=key_hash, name="Key 1", user_id=1)
        key2 = ApiKey(key_hash=key_hash, name="Key 2", user_id=1)

        db.add(key1)
        await db.flush()

        db.add(key2)
        with pytest.raises(Exception):
            await db.flush()
