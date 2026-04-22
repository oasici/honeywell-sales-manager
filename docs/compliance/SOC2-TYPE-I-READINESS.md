# SOC 2 Type I Readiness Package — Honeywell Sales Suite v3

> **Scope**: Trust Services Criteria covered by this release. SOC 2 Type II
> observation window follows once Type I is signed off.
> **Status**: Readiness package, not an audit report. Treat as evidence
> checklist when an auditor is engaged.

## 1. Trust Services Criteria Coverage Matrix

| TSC | Control | Implementation | Evidence Location |
|-----|---------|-----------------|-------------------|
| CC1.1 | Organizational values + code of conduct | `docs/compliance/CODE-OF-CONDUCT.md` | repo |
| CC1.2 | Board / executive oversight | Quarterly security review minutes | engineering lead notes |
| CC2.1 | Information + communication | Slack #security channel, weekly digest | Slack archive |
| CC2.2 | Internal communication | `docs/RUNBOOKS/` incident playbooks | repo |
| CC3.1 | Risk assessment annually | `docs/compliance/RISK-REGISTER.md` | repo |
| CC4.1 | Control monitoring (continuous) | Sentry, Grafana, app audit logs | prod dashboards |
| CC5.1 | Control implementation | This document + automated evidence endpoint | `GET /api/v1/compliance/evidence` |
| CC6.1 | Logical access | JWT + RBAC + field permissions | `backend/app/core/dependencies.py` |
| CC6.2 | Access provisioning | `POST /api/v1/users` + audit trail | `backend/app/api/v1/users.py` |
| CC6.3 | Access removal | `PATCH /users/{id}` sets `is_active=false` + session revocation | `backend/app/api/v1/users.py`, session model |
| CC6.6 | Encryption in transit | HTTPS only via Render + HSTS | `render.yaml` |
| CC6.7 | Encryption at rest | Fernet for secrets, Postgres at-rest (Render managed) | `backend/app/core/crypto.py` |
| CC6.8 | Change control + approvals | GitHub branch protection + required reviews | GitHub settings |
| CC7.1 | Vulnerability management | `pip audit`, Dependabot, quarterly pentest | CI logs |
| CC7.2 | Incident response | `docs/RUNBOOKS/incident-response.md` | repo |
| CC7.3 | Recovery procedures | Render automated backups + docs/RUNBOOKS/dr.md | repo |
| CC8.1 | Change management | Feature flags + Alembic migrations | `backend/alembic/versions/`, `config.py` |
| CC9.1 | Business continuity | RTO 4h / RPO 1h documented | `docs/compliance/BCP.md` |
| A1.1 | Availability commitments | Uptime SLO 99.5%, status page | `docs/compliance/SLA.md` |
| A1.2 | System monitoring | `/api/health`, metrics, alerts | `backend/app/api/v1/audit.py` |
| A1.3 | Environmental protections | Render infra (AWS-backed) | Render Trust Center |
| C1.1 | Confidentiality of data | Classification field on Customer (`data_classification`) | `backend/app/models/customer.py` |
| C1.2 | Disposal of confidential data | KVKK retention job + deletion workflow | `tasks/scheduler.check_data_retention_task` |
| PI1.1 | Processing integrity | Unit + integration tests + ERP mapping hashes | `backend/tests/`, `services/erp/mapping_engine.py` |
| P1.1 | Privacy notice | Posted at `/privacy` landing | `frontend/src/features/landing/` |
| P2.1 | Choice + consent | KVKK consent capture on customer | `customer.kvkk_consent*` columns |
| P4.1 | Use of personal information | AI Trust Layer scrubs PII before LLM | `backend/app/services/ai_trust.py` |
| P5.1 | Access request handling | `GET /compliance/export/{customer_id}` | `backend/app/api/v1/compliance.py` |
| P6.1 | Disclosure + notification | Breach workflow model | `backend/app/models/breach_notification.py` |

## 2. Control Narratives

### 2.1 Logical Access (CC6.1 – CC6.3)
- **Authentication**: PBKDF2 + bcrypt password hashing, JWT access tokens
  (30 min) + refresh tokens (7 d), HttpOnly cookies + CSRF token, rate-limit
  5 login/min.
- **Authorization**: `UserRole` enum (`sales_rep | sales_manager |
  operations`), `require_role` dependency on every mutating endpoint.
  Field-level permissions via `FEATURE_FIELD_PERMISSIONS`.
- **Session revocation**: `UserSession` table records active tokens; logout
  and password change purge rows.
- **MFA**: enabled per user via time-based OTP (see `docs/RUNBOOKS/mfa.md`).

### 2.2 Change Management (CC8.1)
- All backend changes land via GitHub PR with required code-review + CI.
- Schema changes use Alembic migrations (`backend/alembic/versions/`); no
  manual DDL in production.
- Feature flags (`FEATURE_*`) gate all new capabilities — default off.
- Release tags + changelog.

### 2.3 Data Protection (CC6.6 / CC6.7)
- TLS 1.2+ enforced by Render.
- Secrets encrypted with Fernet (`backend/app/core/crypto.py`), key rotation
  supported via `ENCRYPTION_KEY_PREVIOUS`.
- ERP credentials, email passwords, API tokens stored encrypted.
- `Field Audit Trail` (FEATURE_FIELD_AUDIT) captures every scalar attribute
  change with actor + timestamp for regulated customers.

### 2.4 Privacy & AI Trust (P4.1)
- **AI Trust Layer** (`backend/app/services/ai_trust.py`) masks PII (TC
  Kimlik No, VKN, IBAN, credit card, phone, e-mail) before Claude sees the
  payload; responses are re-hydrated via the reversible token map.
- Audit records produced per prompt: SHA-256 of the original prompt plus a
  count of PII hits by type. No raw PII is logged.

### 2.5 Availability (A1.1 – A1.3)
- Render-hosted on AWS with automated daily backups (14-day retention).
- `/api/health` returns database + Redis status.
- Uptime target 99.5% monthly; status page at `status.honeywell-sales.com`.

### 2.6 Monitoring & Incident Response (CC7.1 – CC7.3)
- Sentry DSN for exception capture.
- Structured logs to stdout (Render Log Stream) with request_id.
- Incident playbook: `docs/RUNBOOKS/incident-response.md`.
- Post-mortems stored in the same directory.

### 2.7 Vendor Management
- Subprocessors list: Anthropic, Render, Qdrant Cloud (opt-in), Sentry.
- Each has a signed DPA; records stored in Drive folder *Vendor DPAs*.

## 3. Auditor Evidence Requests

Auditors typically request the artifacts below. All are either in the repo
or fetchable through the `/api/v1/compliance/evidence` endpoint (manager
role required):

- [x] Org chart + role descriptions (`docs/compliance/ROLES.md`)
- [x] Access control matrix export (`/compliance/evidence?type=access`)
- [x] User provisioning / deprovisioning log (`audit_logs` table)
- [x] Change management PR sample (last 30 days)
- [x] Incident ticket sample (last 90 days)
- [x] Backup restoration test log (`docs/RUNBOOKS/dr-test-log.md`)
- [x] Penetration test summary (annual; last run: 2025-11)
- [x] Vulnerability scan output (`pip-audit.json`, `npm-audit.json`)
- [x] AI Trust Layer audit sample (`/compliance/evidence?type=ai_trust`)
- [x] Field-level audit sample (`/compliance/evidence?type=field_audit`)

## 4. Gap Log (for Type II readiness)

| # | Gap | Owner | Target |
|---|-----|-------|--------|
| 1 | Formal BCP tabletop exercise | Platform | 2026-Q3 |
| 2 | SSO (SAML) rollout | Platform | 2026-Q3 |
| 3 | Automated access recertification quarterly | Security | 2026-Q3 |
| 4 | Subprocessor review cadence (semi-annual) | Legal | 2026-Q4 |
| 5 | Continuous compliance dashboard (Drata / Vanta) | Platform | 2026-Q4 |

## 5. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-27 | Platform | Initial v3 readiness package |
