"""Email-feature hardening fixes — tests (audit 2026-06-02).

Encodes the invariants the fixes restore:
  * E1 — a row built from a fetched message carries sender_auth_status,
         tenant_id, and attachments_json (the scheduled poll used to drop
         all three).
  * E2 — an infected attachment is neutralized (text/heuristic_parts
         cleared, av_status recorded) and the email can't auto-quote.
  * E6 — internal-domain senders are skipped on the shared path.
  * scheduler — _run_imap_poll routes through the shared ingest helper and
         stamps the mailbox owner's tenant.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.email_request import EmailRequest
from app.models.setting import Setting
from app.models.user import User
from app.services.email_av_scanner import AvVerdict
from app.services.email_ingestion_service import ingest_fetched_email
from app.services.email_processing_service import _auto_quote_eligible


def _fetched_item(**overrides) -> dict:
    item = {
        "message_id": "msg-ext-1",
        "from_addr": "buyer@acme-customer.com",
        "subject": "RFQ",
        "body": "5x C7061A1012 please",
        "html_body": None,
        "is_read": False,
        "attachments": [],
        "raw_attachments": [],
        "sender_auth_status": "pass",
    }
    item.update(overrides)
    return item


class TestIngestStampsFields:
    @pytest.mark.asyncio
    async def test_row_carries_auth_tenant_attachments(self, db, admin_user):
        item = _fetched_item(
            attachments=[
                {
                    "filename": "rfq.xlsx",
                    "text": "C7061A1012",
                    "heuristic_parts": [{"part_code": "C7061A1012", "quantity": 5}],
                }
            ],
        )
        row = await ingest_fetched_email(db, item, tenant_id=7, assigned_to=admin_user.id)
        assert row is not None
        assert row.tenant_id == 7
        assert row.assigned_to == admin_user.id
        assert row.sender_auth_status == "pass"
        assert row.attachments_json is not None and "C7061A1012" in row.attachments_json
        # auth=pass, no AV infection -> not forced to review
        assert row.review_status is None

    @pytest.mark.asyncio
    async def test_unauthenticated_sender_routes_to_review(self, db, admin_user):
        row = await ingest_fetched_email(
            db, _fetched_item(message_id="msg-noauth", sender_auth_status="none"),
            tenant_id=1, assigned_to=admin_user.id,
        )
        assert row.sender_auth_status == "none"
        assert row.review_status == "pending_review"


class TestSkips:
    @pytest.mark.asyncio
    async def test_duplicate_message_id_skipped(self, db):
        db.add(EmailRequest(message_id="dupe-1", from_address="x@acme-customer.com", status="new"))
        await db.flush()
        row = await ingest_fetched_email(
            db, _fetched_item(message_id="dupe-1"), tenant_id=1, assigned_to=1
        )
        assert row is None

    @pytest.mark.asyncio
    async def test_internal_domain_skipped(self, db, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(
            type(settings), "internal_domains_list",
            property(lambda self: ["honeywell-internal.com"]),
            raising=False,
        )
        row = await ingest_fetched_email(
            db,
            _fetched_item(message_id="int-1", from_addr="bot@honeywell-internal.com"),
            tenant_id=1, assigned_to=1,
        )
        assert row is None


class TestAvScanWiring:
    @pytest.mark.asyncio
    async def test_infected_attachment_neutralized_and_flagged(self, db, admin_user, monkeypatch):
        def fake_scan(attachments):
            return [
                AvVerdict(filename=fn, status="infected", backend="clamav", details="Eicar-Test")
                for fn, _ in attachments
            ]

        monkeypatch.setattr(
            "app.services.email_av_scanner.scan_attachments", fake_scan
        )
        item = _fetched_item(
            message_id="av-1",
            attachments=[
                {
                    "filename": "evil.xlsx",
                    "text": "C7061A1012 malware payload",
                    "heuristic_parts": [{"part_code": "C7061A1012", "quantity": 1}],
                }
            ],
            raw_attachments=[("evil.xlsx", b"PK\x03\x04 ...bytes...")],
        )
        row = await ingest_fetched_email(db, item, tenant_id=1, assigned_to=admin_user.id)
        assert row is not None
        assert row.parse_skipped_reason == "av_infected"
        assert row.review_status == "pending_review"
        import json

        payload = json.loads(row.attachments_json)
        entry = payload[0]
        assert entry["av_status"] == "infected"
        assert entry["text"] == ""          # malicious text stripped
        assert entry["heuristic_parts"] == []  # parts not extracted from infected file

    @pytest.mark.asyncio
    async def test_clean_default_scanner_no_behaviour_change(self, db, admin_user):
        # default _NoopScanner -> "unscanned", never infected
        item = _fetched_item(
            message_id="av-clean-1",
            attachments=[{"filename": "rfq.xlsx", "text": "C7061A1012", "heuristic_parts": []}],
            raw_attachments=[("rfq.xlsx", b"bytes")],
        )
        row = await ingest_fetched_email(db, item, tenant_id=1, assigned_to=admin_user.id)
        assert row.parse_skipped_reason is None
        assert row.review_status is None


async def _mk_manager(db, email: str, tenant_id: int) -> User:
    u = User(
        tenant_id=tenant_id,
        email=email,
        full_name="Mgr",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


class TestListTenantIsolation:
    @pytest.mark.asyncio
    async def test_manager_list_excludes_other_tenant_email(
        self, client: AsyncClient, db: AsyncSession
    ):
        mgr_a = await _mk_manager(db, "mgr_a@test.com", tenant_id=1)
        mgr_b = await _mk_manager(db, "mgr_b@test.com", tenant_id=2)

        own = EmailRequest(
            message_id="own-a", from_address="x@acme-customer.com",
            status="new", tenant_id=1, assigned_to=mgr_a.id,
        )
        foreign = EmailRequest(
            message_id="foreign-b", from_address="y@acme-customer.com",
            status="new", tenant_id=2, assigned_to=mgr_b.id,
        )
        db.add_all([own, foreign])
        await db.commit()
        await db.refresh(own)
        await db.refresh(foreign)

        token = create_access_token({"sub": str(mgr_a.id)})
        resp = await client.get(
            "/api/v1/emails/", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert own.id in ids                # E3 — sees own tenant
        assert foreign.id not in ids        # E3 — must NOT see tenant 2


class TestAutoQuoteGateAv:
    def test_av_infected_blocks_auto_quote(self):
        email = SimpleNamespace(
            parse_skipped_reason="av_infected",
            sender_auth_status="pass",
            attachment_pages_truncated=False,
            first_time_sender=False,
        )
        eligible, reason = _auto_quote_eligible(email, {"parts": []})
        assert eligible is False
        assert reason == "av_infected"


class TestSchedulerPollParity:
    @pytest.mark.asyncio
    async def test_scheduled_poll_stamps_owner_tenant_and_auth(self, db, admin_user, monkeypatch):
        # Record the mailbox owner (as the settings save path now does).
        db.add(Setting(key="email_owner_user_id", value=str(admin_user.id)))
        await db.commit()

        import app.tasks.scheduler as sched
        import app.api.v1.emails as emails_mod

        async def fake_creds(_db):
            return {
                "email_address": "mailbox@company.com",
                "email_password": "x",
                "imap_host": "imap.company.com",
                "imap_port": 993,
            }

        def fake_fetch(host, port, addr, pw, last_uid):
            return [_fetched_item(message_id="sched-1", sender_auth_status="none")]

        monkeypatch.setattr(sched, "_get_imap_credentials", fake_creds)
        monkeypatch.setattr(emails_mod, "_fetch_emails_via_imap", fake_fetch)

        saved = await sched._run_imap_poll(db)
        assert saved == 1

        row = (
            await db.execute(
                select(EmailRequest).where(EmailRequest.message_id == "sched-1")
            )
        ).scalar_one()
        # The pre-fix scheduler left all three NULL -> auth-gate bypass.
        assert row.tenant_id == admin_user.tenant_id
        assert row.assigned_to == admin_user.id
        assert row.sender_auth_status == "none"
        assert row.review_status == "pending_review"
