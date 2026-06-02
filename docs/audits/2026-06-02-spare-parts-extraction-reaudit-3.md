# Spare-Part Extraction → Match → Price → Quote — Third Audit

> **Date:** 2026-06-02 (pass 3) · **Scope:** the same chain, re-audited *after* the R1–R5 remediation. Adversarial pass focused on what the first two audits and the R1–R5 fixes did **not** cover.
> **Standard:** zero tolerance — a wrong part, wrong quantity, or wrong price must never reach a quote *or the customer*.
> **Method:** fresh first-hand read of the current tree; every claim has a `file:line` verified at audit time.
> **Status:** ✅ **REMEDIATED 2026-06-02** (T3→T1→T2→T4→T5, test-first). See "Remediation status".

---

## Remediation status (executed 2026-06-02)

| # | Sev | Fix | Tests |
|---|---|---|---|
| T3 | HIGH | `approve_quote` now rejects any quote with an unconfirmed (`is_confirmed=False`) or unpriced (`unit_price<=0`) line via `_assert_lines_confirmed_and_priced`; a manager may override with `?force=true`, which is **audit-logged** (`quote_approved_override`). `send_quote` blocks any `0.00` line as defence-in-depth. The is_confirmed safety net is now binding. | `test_quote_service::TestApproveQuote` (+force/unconfirmed/unpriced cases) |
| T1 | HIGH | `resolve_part_code` resolves only `is_active=True` parts (inactive → `unknown`); `quote_service` lookups take `active_only=True` on every from-email path. A discontinued SKU no longer auto-quotes; a stale `catalog_part_id` to a now-inactive part routes to review. | `test_spare_parts_audit3_fixes::TestT1InactiveParts` |
| T2 | MED | `dedupe_parsed_parts` collapses same-canonical-code parts into one line (summed quantity, flagged `quantity_suspect`+`duplicate_merged` → review). Applied before the gate (so R1 catches it) and at line creation (legacy safety). | `::TestT2Dedup` |
| T4 | MED | `select_price_entry` no longer falls back to an out-of-window price; an expired/future-only price list → no entry → unpriced → review. | `::TestT4ExpiredPrices` |
| T5 | LOW | `_annotate_catalog_sell_prices` converts each catalog price into the quote currency (TRY) before the gate estimate, so the value cap compares like-for-like (best-effort; line price reconciled by R4). | covered via R4 conversion path |

---

## 0. Re-confirmation
The 14 original findings (P1–P3, Q1–Q5, M1–M2) and the 5 re-audit findings (R1–R5) are verified still closed in the current code: no cost-pricing, resolver-verdict-first matching with score guard, header-aware bounded quantities, normalized dedup, conflict/suspect now enforced at the gate + line, catalog-priced value-cap, currency conversion, thread-trim input cap, Decimal money.

This third pass found **5 new issues** — two HIGH — that sit at the *edges* the prior passes didn't reach: catalog lifecycle, intra-extraction duplicates, and the **approval/send** step where the review flags are supposed to bite.

---

## 1. HIGH

### T1 — Discontinued (`is_active=False`) parts resolve and auto-quote
- **Where:** `part_catalog_resolver.resolve_part_code` queries `select(SparePart.id, SparePart.honeywell_code)` with **no `is_active` filter** (`part_catalog_resolver.py:144,157,162,175`). `quote_service._find_spare_part_by_id` (`:697`) and `_find_spare_part_by_code` (`:701`) also don't filter. Only `parts_matcher._get_cached_catalog` filters `is_active.is_(True)` (`parts_matcher.py:42`).
- **What's wrong:** an inactive/discontinued SKU with an exact code resolves as `catalog_status="exact"`, passes `_auto_quote_eligible`, and `create_quote_from_email` prices it (`is_confirmed=True`) — the system **auto-quotes a part it no longer sells**. The inconsistency is the tell: the fuzzy matcher won't even *suggest* an inactive part, but the exact/normalized resolver path (the one the gate trusts) quotes it.
- **Impact:** a confirmed, customer-facing quote line for a discontinued part. Classic zero-tolerance violation.
- **Fix:** filter `is_active = True` in `resolve_part_code` (resolution → `unknown` for inactive) and in both `quote_service` lookups; an inactive stale `catalog_part_id` then routes to review.

### T3 — Approval / send never enforce the line review flags
- **Where:** `quote_service.approve_quote` (`:170-206`) generates the PDF and sets `APPROVED` with **no check** on `QuoteItem.is_confirmed` or `unit_price > 0`. `quotes.py::send_quote` (`:357-382`) gates only on `status in (approved, sent)` + a recipient.
- **What's wrong:** every `is_confirmed=False` / unpriced-`0.00` line that P3 / Q5 / R1 / R4 deliberately produced "to force review" can be **approved and emailed to the customer** unchanged. The review signal is advisory exactly where it must be binding. A quote with an unverified SKU, a quantity-conflict line, or a `0.00` unpriced line can reach the customer if the operator approves without scrutiny.
- **Impact:** the whole is_confirmed-based safety net (the spine of the prior remediations) is unenforced at the decisive step.
- **Fix:** `approve_quote` (and `send_quote` as defence-in-depth) must reject when any line is `is_confirmed=False` or `unit_price <= 0`, with a clear "N lines need confirmation/pricing" error; a manager override should be explicit + audit-logged.

---

## 2. MEDIUM

### T2 — Intra-extraction duplicate codes aren't deduped
- **Where:** `_merge_heuristic_parts` (`email_processing_service.py`) dedups attachment-vs-LLM by normalized code, but nothing dedups **LLM-vs-LLM** or repeated codes within one source. `quote_service._create_items_with_matching` iterates parsed parts 1:1 → one line each.
- **What's wrong:** if the extractor emits the same code twice (e.g. body says it twice, or a non-hyphen variant the normalizer doesn't catch — spaces vs none is handled, but e.g. `C7061A1012` and `C7061/A1012`), the quote gets **two lines for one physical part** with split quantities. No merge, no flag.
- **Fix:** collapse parsed parts by normalized/canonical code before line creation (sum quantities or flag), reusing the resolver's `_normalize` / `canonical_part_code`.

### T4 — An expired-only price list still quotes the expired price
- **Where:** `part_pricing.select_price_entry:65` — `valid = [e for e in entries if _is_valid(e, today)] or entries`.
- **What's wrong:** when **no** price entry is currently in-window (all expired, or all future-dated), the `or entries` fallback selects an **out-of-window** price (most recent by `valid_from`). For zero tolerance, quoting an expired price silently is wrong — it should route to review (unpriced) instead.
- **Fix:** when no in-window entry exists, return `None` → `resolve_unit_price` → unpriced → line unconfirmed for review (don't fall back to expired/future prices).

---

## 3. LOW

### T5 — Gate value-cap estimate is currency-agnostic (known residual from R2)
- **Where:** `_annotate_catalog_sell_prices` stamps the raw catalog price; `estimate_quote_total` sums it; the cap (`auto_quote_max_amount`) is compared without currency alignment.
- **What's wrong:** a USD catalog estimate compared to a TRY cap under-counts (~30×), so the "big deal → human" cap can still let a large order through. The *line* price is currency-correct (R4); only the *gate estimate* isn't.
- **Fix:** convert the estimate into the tenant/quote currency before the cap comparison (reuse `currency_service`), or define the cap in the catalog currency.

---

## 4. Honest bottom line
The chain itself (extract → match → price) is in good shape after R1–R5. The remaining zero-tolerance gaps are at the **boundaries**: a discontinued part can still be resolved and auto-quoted (**T1**), and — most importantly — the review flags that all the prior fixes rely on are **not enforced at approval/send** (**T3**), so a flagged line can still reach the customer. T2/T4 are correctness edges; T5 is a known residual. **T1 and T3 should be fixed before calling this feature zero-tolerance.**

## 5. Remediation plan (test-first, by risk)
1. **T3** — `approve_quote`/`send_quote` reject unconfirmed or non-positive-price lines (explicit, audited override only). *Highest leverage: it makes every prior is_confirmed fix actually binding.*
2. **T1** — `is_active=True` filter in `resolve_part_code` + both `quote_service` lookups; tests: inactive exact code → `unknown` / unpriced + not eligible.
3. **T2** — dedup parsed parts by canonical code before line creation; test: duplicate code → one line, summed/flagged.
4. **T4** — no expired/future-price fallback → unpriced; test: expired-only list → unpriced + review.
5. **T5** — currency-align the gate estimate; test: USD estimate vs TRY cap converts before compare.

**Files of record:** `part_catalog_resolver.py`, `quote_service.py`, `quotes.py`, `part_pricing.py`, `email_processing_service.py`, `tenant_settings_service.py`. Prior: `2026-06-01-spare-parts-extraction-audit.md`, `2026-06-02-spare-parts-extraction-reaudit.md`.
