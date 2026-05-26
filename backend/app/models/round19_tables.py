"""SQLAlchemy registrations for the Round-19 Phase 4 + Phase 5 tables.

These tables are created by the alembic migrations
``20260629_phase4_hardening`` and ``20260627_phase2_hardening``.
Production DBs apply them via ``alembic upgrade head``.

The *test* fixture in ``tests/conftest.py`` uses
``Base.metadata.create_all()`` which only knows about models
registered against ``Base``. Pre-this-file, the Round-19 tables
were invisible to that path, so endpoint integration tests
failed with ``UndefinedTableError``.

Each model carries only the columns the test layer + service
helpers actually touch. We're not chasing full ORM ergonomics here
— the service modules use raw SQL via ``sqlalchemy.text(...)`` for
these tables, so a thin registration is enough.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantDek(Base):
    """F-001 per-tenant data encryption key."""

    __tablename__ = "tenant_dek"

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_version: Mapped[str] = mapped_column(String(40), nullable=False, default="env-v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdminActionNonce(Base):
    """F-005 one-shot nonce for destructive admin ops."""

    __tablename__ = "admin_action_nonces"

    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SignOtpToken(Base):
    """F-006 e-Sign OTP token row."""

    __tablename__ = "sign_otp_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_used: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ua_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class UserRoleGrant(Base):
    """F-011 many-to-many user-role assignment."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(40), primary_key=True)
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class KvkkExportRequest(Base):
    """F-023 two-person KVKK export state machine."""

    __tablename__ = "kvkk_export_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_lookup: Mapped[str] = mapped_column(String(320), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    requested_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmailOptout(Base):
    """F-024 unsubscribe registry (per-tenant, per-recipient, per-sequence)."""

    __tablename__ = "email_optouts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="unsubscribe_link")
    sequence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unsubscribe_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)


class TokenBlocklist(Base):
    """F-013 JTI blocklist persistent layer."""

    __tablename__ = "token_blocklist"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    exp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)


class WorkflowExecutionLog(Base):
    """F-015 cycle/depth forensic ledger."""

    __tablename__ = "workflow_execution_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    root_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ApprovalRulePendingChange(Base):
    """F-010 meta-approval pending queue."""

    __tablename__ = "approval_rule_pending_changes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # change_payload is JSONB at the DB level; we declare Text here for
    # SQLite compatibility in test infrastructures, with the
    # alembic migration enforcing JSONB on PG.
    change_payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalDecision(Base):
    """F-018 per-approver decision ledger."""

    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    decider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
