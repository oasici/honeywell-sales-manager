# Logo Tiger / Netsis Integration Cookbook

Reference for onboarding a Logo partner endpoint against the v3 ERP
Connector. Use this document when opening a sandbox request with a Logo
reseller.

## 1. What we need from the Logo partner

1. **XML-RPC endpoint URL** — typically one of:
   - `https://<host>/api/v1/logo-ws.svc`
   - `https://<host>/xmlrpc`
   - `https://<host>/tiger-xmlrpc`
2. **Service user credentials** (username + password).
3. **Method catalogue** — the exact method names exposed by the partner's
   wrapper. Names may differ by Logo version and customization.
4. **Character encoding** confirmation. Default assumption: Windows-1254
   payloads that the server transparently converts to UTF-8.

## 2. Methods we rely on

Aliases the adapter uses internally → Logo method name:

| Adapter alias | Default method | Purpose |
|----------------|----------------|---------|
| `login` | `Login(username, password)` | Obtain session reference |
| `list_customers` | `ListCustomers(since, offset, page_size)` | Page cari records |
| `list_items` | `ListItems(since, offset, page_size)` | Page item master records |
| `list_stock` | `ListStock(codes[])` | On-hand stock per warehouse |
| `create_invoice` | `CreateInvoice(payload_dict)` | v1.1 invoice push |

If the partner uses different names (e.g. `wsListCari`, `SPR_ITEMS`), set
them via `ERPConnection.credentials.method_overrides`:

```json
{
  "username": "svc-user",
  "password": "••••••••",
  "method_overrides": {
    "login": "wsLogin",
    "list_customers": "wsListCari",
    "list_items": "wsListStok"
  }
}
```

The adapter loads these overrides when the connector is built.

## 3. Row field conventions

### ListCustomers row (typical)

| Field | Notes |
|--------|-------|
| `LogicalRef` | Primary key. We use as `external_id`. |
| `Code` | Short code; fallback external_id if `LogicalRef` missing. |
| `Definition_` / `Definition` | Company display name (the trailing underscore is Logo's convention). |
| `TaxNr` / `TCKN` | VKN or TCKN. |
| `EMailAddr` | Primary email. |
| `Telephones` | CSV of phone numbers; first one kept. |
| `Address1` / `City` | Free text. |
| `Active` | **0 = active, 1 = passive.** Some partners invert. |
| `ModifiedDate` | `YYYY-MM-DD HH:MM:SS` in local TZ. |

### ListItems row (typical)

| Field | Notes |
|--------|-------|
| `LogicalRef` / `Code` | External id + SKU. |
| `Name` / `Definition_` | Display name. |
| `UnitSetCode` | Unit of measure (`adet`, `kg`, …). |
| `ListPrice` + `CurrencyCode` | List price + ISO currency. |
| `VatRate` | Numeric VAT. |
| `ItemClass` | Category. |
| `ModifiedDate` | Same format as above. |

### ListStock row

| Field | Notes |
|--------|-------|
| `Code` | Matches `ListItems.Code`. |
| `WarehouseRef` / `WarehouseCode` | Numeric warehouse id. |
| `OnHand` | Current qty. Can be negative in some setups. |
| `UnitSetCode` | UOM. |

## 4. Sandbox onboarding checklist

- [ ] Obtain endpoint URL + credentials from partner.
- [ ] Create an `ERPConnection` with `type="logo"` via
      `POST /api/v1/erp/connections` and pass overrides if needed.
- [ ] Run `POST /api/v1/erp/connections/{id}/test` — expects 200 with a
      non-empty `session_ref`.
- [ ] Trigger `POST /api/v1/erp/connections/{id}/sync` with
      `{ "entity": "customer", "mode": "full" }`.
- [ ] Confirm `erp_entity_mappings` rows are being created.
- [ ] Run `"entity": "product"` and then `"entity": "stock"`.
- [ ] Flip `sync_cron` on (e.g. `0 */2 * * *`) and confirm the scheduler
      job fires by tailing logs for `ERP cron dispatched`.
- [ ] Invite the partner to verify their audit logs on their side.

## 5. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Logo method X not offered by this endpoint` | Partner wrapper uses a different method name. Add the override. |
| `Logo authentication rejected` | Service user disabled or wrong database mapping; ask partner to confirm. |
| `Logo rate limit` | Partner enforces throttling; our backoff waits `retry_after` seconds. |
| Empty `fetch_customers` output | `since` filter too strict — trigger a full sync once. |
| Garbled Turkish characters | Partner returning Windows-1254 without charset header. Ask for UTF-8 response. |
| `UniqueConstraint uq_erp_mapping_external` violation | Partner re-assigning existing `LogicalRef` to new row (rare). Escalate. |

## 6. Production-readiness gate

Before flipping `FEATURE_ERP_CONNECTOR=true` in production:

1. Integration tests green (`tests/test_logo_adapter.py`).
2. At least one staging sync run with > 1000 customer rows completed
   without conflicts.
3. Rollback runbook rehearsed (uninstall connection → delete
   `erp_entity_mappings` rows → rerun clean).
4. Monitoring alert for `erp.sync.failed` count > 3/hour.
5. Legal confirmed the Logo partner DPA covers their sub-processing.
