# Real RFQ E2E Test — Setup & Findings

> **Date:** 2026-06-02 · **Scope:** four real customer RFQ emails run through the live extraction → match → price → quote pipeline.
> **Harness:** `backend/tests/test_real_rfq_emails.py` (6 tests, all green). The only stubbed step is the Claude LLM extraction (no API key in CI) — replaced with the structured output Claude would return per body. Resolver, dedup, catalog pricing, eligibility gate, and auto-quote are all exercised for real against a seeded catalog.

## The four samples
| # | Subject | From | Parts | Notable |
|---|---|---|---|---|
| 1 | Yedek Parça Talep | birkanege.durukan@honeywell.com | 764744×2, 581239×3, HDZWM2×1 | Turkish, "2 adet" |
| 2 | hONEYWELL YEDEK PARÇA | …honeywell.com | 764744×2, 581239×3, **HDZ WM2**×1 | space variant |
| 3 | Spare Part | …honeywell.com | 764744×2, 581239×3, HDZ WM2×1 | English, "2qty" |
| 4 | [External] Türbinmetre Fyat Talebi | neslihan.halat@tanap.com | 3× Türbinmetre, **no codes** (spec table) | external, code-less |

## What works (verified end-to-end)
- Emails 1–3 (known sender, exact codes) → 3 parts resolved, correct quantities (2/3/1), priced from the **catalog** in TRY, auto-drafted quote with correct line + subtotal (10 000 TRY), all lines confirmed.
- `HDZ WM2` (space) **normalizes** to catalog `HDZWM2` → one canonical line (T2/Q3 holds).
- Email 4 (no part codes) → nothing resolves → the gate **refuses to auto-quote** and routes to review. ✅ zero-tolerance behavior.

## Findings (real-world)

### F-A (HIGH) — the regex/heuristic extractors don't recognize real Honeywell codes  ·  ✅ FIXED 2026-06-02
**Resolution:** rather than widening the regex (which can't tell `764744` from a price/year), extraction is now **catalog-aware** — new `app/services/catalog_code_scanner.py` matches email tokens against the *actual uploaded catalog codes*, so it recognizes any code we sell (numeric `764744`, short alnum `HDZWM2`, spaced `HDZ WM2`→`HDZWM2`) with ~zero false positives. Wired into `_parse_email_with_fallback` as an always-on augmentation (merged via the existing dedup path), so codes the LLM misses **and** codes left to the Claude-down regex fallback are recovered with a best-effort line quantity (flagged when uncertain). Tests: `test_catalog_code_scanner.py` (9) + `test_real_rfq_emails::TestClaudeDownCatalogRecovery` (Claude-down → 3 codes recovered → routed to review, not dropped). The shape regex stays intentionally narrow (`TestRealCodeExtractionGap`).

Original finding (for the record):
`_TABULAR_PART_PATTERN` and `regex_fallback_parse` match **none** of `764744`, `581239`, `HDZWM2`, `HDZ WM2`. Consequences:
- **Claude-down fallback** (`regex_fallback_parse`) returns `parts=[]` and classifies these as *not* a spare-part request → a real RFQ is silently dropped during an Anthropic outage.
- **Attachment-table extraction** (`extract_rows_as_parts`, used for Excel/CSV/PDF) won't find these codes; on the türbinmetre table it actually mis-picks `DN100` (a diameter) as a "part code".
- Normal operation is fine **only because the LLM extracts the codes** and the resolver looks them up by string (no regex). The heuristic/fallback safety net is effectively blind to the customer's real code formats.
- **Fix needs domain input:** the real code universe (6-digit numeric like `764744`; short alnum like `HDZWM2`; classic `C7061A1012`; hyphenated `51309276-150`). Broadening the pattern risks false positives (years, quantities, prices), so it should be column/context-aware (header-detected code column) rather than a looser free-text regex.

### F-B (MED, config) — `honeywell.com` is in `internal_domains_list`
Emails 1–3 are *from* `birkanege.durukan@honeywell.com`. The ingestion internal-domain filter (`email_ingestion_service._is_internal`) would **skip** them in this deployment (default `internal_domains_list = ['honeywell.com', 'honeywell.com.tr']`). If these internal-account-manager forwards are real inbound RFQs, the deployment must remove `honeywell.com` from `INTERNAL_EMAIL_DOMAINS` (or forward from a non-honeywell address). The external TANAP email (email 4) is unaffected.

### F-C (note) — code-less spec RFQs (email 4) are review-only by design
The türbinmetre RFQ has no part numbers, only specs (Tip/Adet/Kapasite/Çap/Basınç). It correctly routes to review — but to *quote* it the operator must map specs → catalog SKUs manually. A future enhancement could fuzzy-match spec descriptions to catalog names (already possible via `parts_matcher` on description), surfaced as review-only suggestions.

## Recommended next steps
1. **F-A** — broaden code recognition (column/context-aware) once the real code-format set is confirmed; regression tests in `test_real_rfq_emails.py::TestRealCodeExtractionGap` will flip when fixed.
2. **F-B** — adjust `INTERNAL_EMAIL_DOMAINS` for the pilot deployment.
3. Re-run the harness against more real samples as they arrive — it's the cheapest way to keep extraction honest.
