# Access Control Matrix

> Generated from `UserRole` enum + `require_role` decorators. Keep in sync
> with any new endpoint gated by a role.

| Domain | Action | sales_rep | sales_manager | operations |
|--------|--------|-----------|----------------|------------|
| Customers | Read | ✅ | ✅ | ✅ |
| Customers | Create / update | ✅ | ✅ | ✅ |
| Customers | Merge / delete | ❌ | ✅ | ✅ |
| Quotes | Create / edit own | ✅ | ✅ | ✅ |
| Quotes | Approve | ❌ | ✅ | ❌ |
| Pricing admin | Read | ✅ | ✅ | ✅ |
| Pricing admin | Tier / customer-specific write | ❌ | ✅ | ✅ |
| Margin rules | Read | ✅ | ✅ | ✅ |
| Margin rules | Update | ❌ | ✅ | ✅ |
| ERP Connector | Read / test | ❌ | ✅ | ✅ |
| ERP Connector | Create / delete | ❌ | ✅ | ❌ |
| ERP Invoice push | Execute | ❌ | ✅ | ✅ |
| Field audit | Read | ❌ | ✅ | ✅ (per-entity only) |
| WhatsApp | Send text / template | ✅ | ✅ | ✅ |
| Operations (MRP) | Movements / transfers | ❌ | ✅ | ✅ |
| Operations (MRP) | Warehouses / BOM | ❌ | ✅ | ✅ |
| Agentic SDR | Run agent manually | ✅ | ✅ | ✅ |
| Marketplace | Plugin catalogue read | ✅ | ✅ | ✅ |
| Marketplace | Install / uninstall plugin | ❌ | ✅ | ❌ |
| Marketplace | Manage subscriptions | ❌ | ✅ | ❌ |
| Compliance | Evidence export | ❌ | ✅ | ❌ |
| Users | Reset password | ❌ | ✅ | ❌ |
| Transcripts | Upload + summarise | ✅ | ✅ | ❌ |

**Break-glass**: production deploy account (`deploy@honeywell`) carries
`sales_manager` role but is guarded by SSO + hardware key + break-glass
auditing. Use only during incident response; every action is captured in
`field_audit_logs` and `audit_logs`.
