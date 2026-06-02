# Spare-Part Extraction from Email — Correctness Audit & Remediation Plan

> **Date:** 2026-06-01 · **Scope:** the email → part extraction → catalog matching → quote line-item → pricing chain ONLY.
> **Standard requested:** zero tolerance — a wrong part code, wrong quantity, or wrong price must never reach a quote.
> **Method:** direct first-hand code review; every finding carries a `file:line` reference verified at audit time.
> **Status:** ✅ **REMEDIATED 2026-06-01.** All five phases below were implemented test-first. See "Remediation status" immediately below. Companion: the broader email-feature audit (IMAP/tenant/security) delivered same day — see "Related" at the bottom.

---

## Remediation status (executed 2026-06-01)

| Phase | Findings | Status | Implementation | Tests |
|---|---|---|---|---|
| 1 — Pricing correctness | P1 | ✅ Done | new `app/services/part_pricing.py` (`resolve_unit_price`: price-list → cost+margin → unpriced; never ≤ cost); wired into `quote_service._create_items_with_matching` + legacy path | `tests/test_part_pricing.py` (8) |
| 2 — Unify matching + confidence guard | P2, P3 | ✅ Done | `quote_service._resolve_line_match`: resolver verdict (gate's engine) is line-item source of truth; `parts_matcher` is a score-guarded fallback (`LINE_ITEM_MATCH_THRESHOLD=80`); sub-threshold leaves SKU unset | `tests/test_quote_line_matching.py` (6) |
| 3 — Quantity integrity | Q1, Q2, Q5 | ✅ Done | `email_attachment_parser.extract_rows_as_parts` rewritten header-aware (Qty/Adet/Miktar, skips line-number col); 10k cap removed → `MAX_REASONABLE_QTY=1_000_000`; `_safe_quantity` bounds + `quantity_suspect` flag in `quote_service` | `tests/test_attachment_quantity.py` (8) |
| 4 — Merge correctness | Q3, Q4 | ✅ Done | `_merge_heuristic_parts` dedups by normalized code; body/attachment qty conflict → `quantity_conflict` + `quantity_suspect` (no silent drop) | `tests/test_merge_heuristic_parts.py` (6) |
| 5 — Resolver hardening | M1, M2 | ✅ Done | `part_catalog_resolver`: full-code digit-only Levenshtein neighbour → `unknown` (OCR letter↔digit still resolves); normalized-key collisions → `unknown` + logged | `tests/test_resolver_hardening.py` (5) |

**Net behavioural change:** a customer quote is now never priced at cost; the SKU on the line is the same one the auto-quote gate evaluated; spreadsheet quantities are read from the real Qty column; hyphen variants no longer double-count; and a code one digit off a real part routes to review instead of being silently substituted. Lines that can't be safely priced/matched are left unconfirmed (`is_confirmed=False`) for human review rather than guessed.

---

## 0. The pipeline under audit

```
inbound email (IMAP)
  → _fetch_emails_via_imap            # raw fetch, sender-auth, attachment parse  (emails.py:835)
  → EmailProcessingService.process_email
      → _parse_email_with_fallback
          → claude_parser.parse_email           # LLM tool-use extraction
          → regex_fallback_parser.regex_fallback_parse   # when Claude down
          → email_attachment_parser.extract_rows_as_parts # Excel/CSV/PDF heuristic
          → _merge_heuristic_parts              # merge LLM + attachment rows
      → part_catalog_resolver.resolve_parsed_parts  # catalog_status: exact/normalized/fuzzy/unknown
      → _auto_quote_eligible                    # the strict gate
      → _auto_create_draft_quote
          → quote_service.create_quote_from_email
              → parts_matcher.match_parts       # ⚠ SECOND, DIFFERENT matcher
              → QuoteItem(quantity, unit_price) # price from cost-basis fields
```

**Headline:** there are **two independent matching engines** (`part_catalog_resolver` for the gate, `parts_matcher` for the actual line item), a **pricing precedence that quotes at cost**, and a **spreadsheet quantity heuristic that captures line numbers**. None is acceptable for a zero-tolerance process.

---

## 1. CRITICAL — wrong PART or wrong PRICE reaches the quote

### P1 — Quotes priced at COST, wrong precedence, no margin applied
- **Where:** `backend/app/services/quote_service.py:350-355` and `:368-373`.
- **What:** customer `unit_price` precedence is `transfer_price → supplier_price → prices[0].net_price`.
- **Why it's wrong:** on `SparePart` (`backend/app/models/spare_part.py:31-34`) `transfer_price` + `supplier_price` sit beside `min_margin_pct` — they are **cost-basis** fields. The authoritative customer price list is `PriceEntry.list_price` / `PriceEntry.net_price` (`backend/app/models/price_entry.py:18-20`). So a cost-tracked part is **quoted to the customer at cost (zero margin)**, and the real price list is only the last-resort fallback. `min_margin_pct` is **never read** in `quote_service`.
- **Impact:** money-losing quotes; inverted price source.
- **Action required:** confirm the business meaning of `transfer_price`; regardless, fix precedence (price list first) and apply margin / never quote below cost.

### P2 — Two divergent matching engines; the "safe" gate is not what picks the SKU
- **Where:** gate = `part_catalog_resolver.resolve_parsed_parts` (Damerau-Levenshtein ≤2, only `exact`/`normalized` may auto-quote). Line item = `quote_service.py:309-345` calling `parts_matcher.match_parts` (rapidfuzz `token_sort_ratio`), then `matches[0]`.
- **What's wrong:** the engine that decides "safe to auto-quote" is a *different* engine from the one that selects `spare_part_id` + price. They can pick different SKUs for the same input.
- **Impact:** an email can pass the gate on one engine's verdict while the quote line is built from another engine's (possibly different) match.

### P3 — `matches[0]` becomes a priced line item regardless of score
- **Where:** `backend/app/services/quote_service.py:337-355`; cutoffs in `backend/app/services/parts_matcher.py:29-30` (`FUZZY_CODE_CUTOFF = 75.0`, `FUZZY_NAME_CUTOFF = 50.0`).
- **What:** the top match's `spare_part_id` + price are written to the line **even at low score**; `is_confirmed = match_score >= AUTO_CONFIRM_THRESHOLD (80)` is only a flag, not a guard.
- **Impact:** a code-less description (e.g. "valve") fuzzy-matching a part *name* at 50% silently gets a real SKU and price on the quote.

---

## 2. HIGH — wrong QUANTITY, or duplicate / dropped parts

### Q1 — Spreadsheet quantity = "first integer in the row" → captures the line-number column
- **Where:** `backend/app/services/email_attachment_parser.py:732-738` (`extract_rows_as_parts`).
- **What:** the first integer ≤ 9999 in a row is taken as the quantity. For the common layout `1 | C7061A1012 | Flame detector | 5 | 1200`, it captures `1` (line number) and **discards the real `5`**. Silent.
- **Live:** wired at `backend/app/api/v1/emails.py:396` and `:990`; flows through `_merge_heuristic_parts` into quote line items.

### Q2 — Quantities ≥ 10,000 silently become 1
- **Where:** same function, `0 < val < 10_000` cap (`email_attachment_parser.py:736`). Bulk orders lose their quantity (`qty or 1` → 1).

### Q3 — Merge double-counts a part on hyphen/space variance
- **Where:** `backend/app/services/email_processing_service.py` `_merge_heuristic_parts` (dedup key = `code.strip().upper()`, not normalized).
- **What:** LLM `C7061A1012` + attachment `C7061-A1012` → **two line items for one physical part** (the resolver would normalize them, but merge runs first).

### Q4 — Merge silently drops the attachment quantity on conflict
- **Where:** same `_merge_heuristic_parts`. When a code appears in both body and spreadsheet with **different** quantities, the LLM/body entry wins and the spreadsheet quantity is discarded — even though the spreadsheet is usually authoritative. No conflict flag.

### Q5 — No quantity bounds at line creation
- **Where:** `backend/app/services/quote_service.py:326` `int(part_req.get("quantity", 1))` — no min/max/sanity check.

---

## 3. MEDIUM — plausible-but-wrong suggestions, latent data bugs

- **M1 — Fuzzy Levenshtein ≤2 maps one valid SKU to another valid SKU.** `part_catalog_resolver.py:183-200`. Dense Honeywell codes (`…1011` vs `…1012`) are 1 edit apart. The auto-quote gate blocks fuzzy, but the operator is shown a confident wrong suggestion to approve.
- **M2 — Normalized-key dict collision hides catalog SKUs.** `part_catalog_resolver.py:162` `norm_to_row = {_normalize(r): r}` silently keeps only the last of two SKUs that normalize identically.
- **M3 — `prices[0].net_price` takes the first price** with no currency/validity ordering (`quote_service.py:354`).
- **M4 — Regex fallback quantity uses a ±30-char first-occurrence window** (`regex_fallback_parser.py:142-155`) and can misattribute across codes. Mitigated: fallback confidence is 0.4, below the 0.7 auto-quote bar, so it always routes to a human — wrong data is shown, not auto-quoted.

---

## 4. What is genuinely solid (build on this)

- **The fully-automated auto-quote gate is strict** (`email_processing_service.py:31-86`, `:202-227`): requires SPF/DKIM/DMARC `pass` + **every** part `exact`/`normalized` + not first-time-sender + under per-tenant amount cap + confidence ≥ 0.7 + review `APPROVED`. Pure auto-quoting only fires on high-confidence exact matches — so most defects above bite the **operator-approved / manual** quote path and the **spreadsheet-quantity** path, not the silent-auto path.
- **Regex fallback cannot auto-quote** (confidence 0.4 < 0.7).
- **Claude tool schema** forces integer quantity + structured fields (`claude_parser.py:24-152`).
- **Resolver tie-break** correctly returns `unknown` on equal-distance ties (`part_catalog_resolver.py:189-191`).

---

## 5. Honest bottom line

The extraction → matching → pricing chain is **not yet "perfect."** Two independent matchers disagree, pricing precedence quotes at cost, and the spreadsheet quantity heuristic captures line numbers. The fully-automatic path is protected by a strict gate; the operator-approved path and all spreadsheet-derived quantities are exposed.

---

## 6. Remediation plan (test-first, ordered by risk)

> Each step: write failing tests that encode the invariant, then make them pass. No behavior change without a test that would have caught the defect.

### Phase 1 — Pricing correctness (P1)  ·  highest business impact
1. Define the single source of truth for **sell price**: `PriceEntry.net_price`/`list_price` first.
2. When only cost (`transfer_price`/`supplier_price`) is available, derive sell price = cost × (1 + `min_margin_pct`); **never** emit a `unit_price` ≤ cost.
3. Tests: "never quote at cost", "price-list takes precedence over cost fields", "margin applied when only cost known", "currency-consistent price selected".

### Phase 2 — Unify matching + confidence guard (P2, P3)
4. Collapse to ONE matcher used by both the gate and `create_quote_from_email` (or make `create_quote_from_email` consume the resolver's already-computed `catalog_part_id`/`catalog_status`).
5. Refuse to auto-populate a line `spare_part_id`+price below a confidence threshold; leave SKU blank → forced review.
6. Tests: gate verdict == line-item SKU; sub-threshold match leaves SKU unset; fuzzy_name@50 never auto-prices.

### Phase 3 — Quantity integrity (Q1, Q2, Q5)
7. Replace the "first integer" heuristic with **header-aware column detection** (Qty / Adet / Miktar / Quantity), ignoring a leading line-number/`#` column.
8. Remove the 10 000 cap; add explicit quantity bounds (e.g. 1 ≤ qty ≤ configurable max) with a review flag on violation.
9. Tests: spreadsheet with a line-number column extracts the real qty; qty ≥ 10 000 preserved; out-of-range → review, not silent 1.

### Phase 4 — Merge correctness (Q3, Q4)
10. Dedup by **normalized** code (reuse `part_catalog_resolver._normalize`).
11. On same-code quantity conflict between body and attachment, **flag for review** instead of silently choosing; surface both values.
12. Tests: `C7061A1012` + `C7061-A1012` → one line; conflicting quantities → conflict flag.

### Phase 5 — Resolver hardening (M1, M2)
13. For `fuzzy_levenshtein`, when the input itself is a structurally-valid Honeywell code, treat a ≤2 match to a *different* valid SKU as `unknown` (don't suggest a real-but-different part).
14. Detect normalized-key collisions in the catalog and surface them (data-quality report) instead of silently dropping.
15. Tests: valid-but-absent SKU near a valid SKU → `unknown`; colliding catalog rows reported.

---

## 7. Related
- Same-day **email-feature security audit** (IMAP credentials, tenant isolation on email read paths, sender-auth header-trust, AV scanner dead code, scheduled-vs-manual ingestion asymmetry). Key cross-refs that also affect extraction trust:
  - Scheduled poll (`scheduler._run_imap_poll`) creates rows with NULL `tenant_id` and NULL `sender_auth_status`, so the F-002 auth gate is bypassed (`_auto_quote_eligible` `if auth and auth != "pass"` is a no-op when `auth is None`).
  - Antivirus scanning (`email_av_scanner.scan_attachments`) is implemented but never called — attachments are parsed unscanned.

**Files of record for this audit:**
`backend/app/services/claude_parser.py`, `regex_fallback_parser.py`, `email_attachment_parser.py`, `part_catalog_resolver.py`, `parts_matcher.py`, `email_processing_service.py`, `quote_service.py`; models `spare_part.py`, `price_entry.py`, `email_request.py`.
