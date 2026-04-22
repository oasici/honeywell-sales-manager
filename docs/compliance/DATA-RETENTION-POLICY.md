# Data Retention Policy

> Effective: 2026-04-27
> Review: annually by Compliance lead.

| Data Class | System of Record | Retention | Deletion Mechanism |
|------------|------------------|-----------|--------------------|
| Customer PII | `customers` table | 7 years after last active engagement OR user DSAR | `customers.data_retention_until` + daily `check_data_retention_task` |
| Quotes / invoices | `quotes`, `invoices` | 10 years (SOX / KVKK) | Soft delete; hard purge on DSAR with legal sign-off |
| AI prompts / responses | not stored | n/a | `ai_trust.audit_record()` keeps SHA-only metadata |
| AI training data | `ai_training_data` | 18 months (quality loop) | rolling delete job |
| Field audit log | `field_audit_logs` | `FIELD_AUDIT_RETENTION_DAYS` (default 3650 = 10y) | partitioned delete |
| Engagement transcripts | `transcripts` | 3 years | nightly cleanup of transcripts not linked to open deals |
| WhatsApp messages | `whatsapp_messages` | 2 years | nightly purge of closed threads |
| ERP sync jobs | `erp_sync_jobs` | 90 days | rolling delete |
| System access logs | `audit_logs` | 1 year | rolling delete |
| Session tokens | `user_sessions` | 7 days | automatic on expiry |
| Backups | Render managed | 14 days | Render policy |

## Disposal Procedures

- **Soft delete**: row keeps `is_active=false` / `deleted_at` timestamp so
  referential integrity survives.
- **Hard delete**: authorized via DSAR workflow. Requires manager + legal
  approval. Logs the deletion event in `audit_logs` AND removes the row.
- **Backup purge**: 14 days after hard delete the row is overwritten in
  cycled backups (Render default).
- **Offboarding**: when a user is deactivated, their authored tasks and
  comments remain (business record); personal notifications and sessions
  are purged within 24 hours.

## KVKK / GDPR Alignment

- **Lawful basis** is captured in `customers.data_processing_purpose`.
- **Right to erasure**: set `customers.deletion_requested_at`; scheduler
  runs the disposal procedure and notifies the data subject via e-mail.
- **Right to access**: `GET /api/v1/compliance/export/{customer_id}` (to be
  wired in Type II phase) returns the structured export.
