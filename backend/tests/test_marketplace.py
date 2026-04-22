"""Marketplace service tests (install + scope + subscription plumbing)."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.marketplace import Plugin, PluginInstallation
from app.services.marketplace import (
    MarketplaceError,
    ScopeDenied,
    add_subscription,
    install_plugin,
    uninstall_plugin,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        plugin = Plugin(
            slug="slack-reporter",
            name="Slack Reporter",
            scopes_json=json.dumps(["opportunities:read", "quotes:read"]),
            events_json=json.dumps(["quote.approved", "opportunity.stage_changed"]),
            is_active=True,
        )
        session.add(plugin)
        await session.flush()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_install_grants_requested_scopes(session: AsyncSession):
    install, token = await install_plugin(
        session,
        plugin_slug="slack-reporter",
        granted_scopes=["opportunities:read"],
        installed_by=None,
    )
    assert install.status == "active"
    granted = json.loads(install.granted_scopes_json)
    assert granted == ["opportunities:read"]
    assert token.startswith("mkt_")


@pytest.mark.asyncio
async def test_install_rejects_unlisted_scope(session: AsyncSession):
    with pytest.raises(ScopeDenied):
        await install_plugin(
            session,
            plugin_slug="slack-reporter",
            granted_scopes=["admin:all"],
            installed_by=None,
        )


@pytest.mark.asyncio
async def test_duplicate_install_blocked_until_uninstall(session: AsyncSession):
    install, _ = await install_plugin(
        session,
        plugin_slug="slack-reporter",
        granted_scopes=["opportunities:read"],
        installed_by=None,
    )
    with pytest.raises(MarketplaceError):
        await install_plugin(
            session,
            plugin_slug="slack-reporter",
            granted_scopes=["opportunities:read"],
            installed_by=None,
        )
    await uninstall_plugin(session, installation_id=install.id)
    # After uninstall we can install again.
    install2, _ = await install_plugin(
        session,
        plugin_slug="slack-reporter",
        granted_scopes=["quotes:read"],
        installed_by=None,
    )
    assert install2.id == install.id
    assert install2.status == "active"


@pytest.mark.asyncio
async def test_add_subscription_rejects_undeclared_event(session: AsyncSession):
    install, _ = await install_plugin(
        session,
        plugin_slug="slack-reporter",
        granted_scopes=["opportunities:read"],
        installed_by=None,
    )
    await session.refresh(install, attribute_names=["plugin"])
    with pytest.raises(ScopeDenied):
        await add_subscription(
            session,
            installation=install,
            event_type="not_declared",
            target_url="https://example.com/webhook",
        )


@pytest.mark.asyncio
async def test_subscription_persists_secret_hash(session: AsyncSession):
    install, _ = await install_plugin(
        session,
        plugin_slug="slack-reporter",
        granted_scopes=["opportunities:read"],
        installed_by=None,
    )
    await session.refresh(install, attribute_names=["plugin"])
    sub = await add_subscription(
        session,
        installation=install,
        event_type="quote.approved",
        target_url="https://example.com/webhook",
        secret="s3cret",
    )
    assert sub.secret_hash and sub.secret_hash != "s3cret"
    assert len(sub.secret_hash) == 64  # sha256 hex
