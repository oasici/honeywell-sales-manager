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
    JSON,
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
    # D-027 — slot for RFC 3161 TSA-signed timestamp (Phase 5 wire).
    tsa_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


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
    # change_payload is JSONB at the DB level. We declare JSON in the
    # model so schema_check accepts the alignment (PG JSON ≡ JSONB via
    # the schema_check synonym list). SQLite test environments fall
    # back to TEXT via SQLAlchemy generic mapping.
    change_payload: Mapped[str] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LoginLockout(Base):
    """D-006 persistent per-account login rate limit."""

    __tablename__ = "login_lockouts"

    email_lower: Mapped[str] = mapped_column(String(320), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_locked_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)


class CrossTenantAttempt(Base):
    """D-010 cross-tenant probe audit log."""

    __tablename__ = "cross_tenant_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_tenant: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_entity: Mapped[str] = mapped_column(String(40), nullable=False)
    attempted_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)


class BackgroundJobDlq(Base):
    """D-019 dead-letter queue for failed background jobs."""

    __tablename__ = "background_job_dlq"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(60), nullable=False)
    # JSONB at the DB level; ``JSON`` here so schema_check accepts the
    # alignment via the JSONB→JSON synonym.
    payload: Mapped[str] = mapped_column(JSON, nullable=False, default="{}")
    error: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActiveSession(Base):
    """D-023 active sessions for logout-everywhere + audit."""

    __tablename__ = "active_sessions"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


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
