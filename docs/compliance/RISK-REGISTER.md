# Risk Register — Honeywell Sales Suite

> Review cadence: quarterly.
> Owner: Platform lead.

| ID | Risk | Inherent | Controls | Residual | Owner |
|----|------|----------|----------|----------|-------|
| R-001 | Credential leakage via log aggregation | High | Log scrubber, Fernet-encrypted secrets, `core/crypto.py` exclusion list | Low | Platform |
| R-002 | ERP credential theft | High | Fernet-per-tenant, rotation via `ENCRYPTION_KEY_PREVIOUS` | Medium | Platform |
| R-003 | LLM PII leakage to vendor | High | `FEATURE_AI_TRUST_LAYER` scrubber + audit log (SHA only) | Low | Platform |
| R-004 | Cross-tenant data exposure | High | `require_role` guards, `tenant_id` scoping on marketplace installs | Low | Platform |
| R-005 | KVKK non-compliance | High | Consent capture, retention job, DSAR endpoint | Medium | Compliance |
| R-006 | Webhook replay / spoof | Medium | HMAC signature (`X-Marketplace-Signature`), secret hash stored | Low | Platform |
| R-007 | Autonomous agent runaway | Medium | No direct send — only drafts; rate limit via event trigger policy | Low | Platform |
| R-008 | Stock desync with ERP | Medium | Idempotent mapping + conflict resolver + domain event audit | Low | Operations |
| R-009 | Denial of service via file upload | Medium | 10MB cap, allow-list of extensions, PDF pages hard-cap | Low | Platform |
| R-010 | Token drift on key rotation | Medium | `MultiFernet` fallback + rotation runbook | Low | Platform |
