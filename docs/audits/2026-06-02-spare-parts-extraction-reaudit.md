# Spare-Part Extraction from Email — Re-Audit (zero tolerance)

> **Date:** 2026-06-02 · **Scope:** the email → part extraction → catalog matching → quote line-item → pricing chain, re-audited after the 2026-06-01 remediation **and** the same-day email-feature hardening (shared ingestion, AV neutralization, per-call input cap, batch throttle).
> **Standard:** zero tolerance — a wrong part, wrong quantity, or wrong price must never reach a quote, and the auto-quote path must refuse anything uncertain.
> **Method:** fresh first-hand code read of the *current* tree; every claim carries a `file:line` verified at audit time. No reliance on the prior audit's conclusions.
>
> **Status:** ✅ **REMEDIATED 2026-06-02** (R1→R2→R4→R3→R5, test-first). See "Remediation status" below.

---

## Remediation status (executed 2026-06-02)

| # | Sev | Fix | Tests |
|---|---|---|---|
| R1 | HIGH | `_auto_quote_eligible` returns `quantity_uncertain` when any part carries `quantity_conflict`/`quantity_suspect`; `_create_items_with_matching` OR-s those flags into `qty_suspect` so the line is `is_confirmed=False` (still priced from catalog). | `test_spare_parts_reaudit_fixes::TestR1*` |
| R2 | HIGH | New `_annotate_catalog_sell_prices` stamps each resolved part's **catalog** sell price onto the parsed dict (prices from catalog, never email) before the gate, so `estimate_quote_total` is no longer always 0 and the per-tenant max-amount cap actually fires. | `::TestR2ValueCap` |
| R4 | MED | `resolve_unit_price_with_currency` reports the price's source currency; `_apply_part_to_resolution` converts catalog→quote currency via `currency_service` and leaves the line **unpriced** if conversion fails — never a silent foreign-currency number. | `::TestR4CurrencyConversion` |
| R3 | MED | Input cap now trims **older thread history** (front), keeping the current email intact (`_bound_llm_input`); the current email is capped on its own only in the pathological case. | `::TestR3InputCapKeepsCurrentEmail` |
| R5 | LOW | Quote line totals + `_recalculate_totals` accumulate in `Decimal` (half-up to cents) then store as float — no float drift across a multi-line quote. | `::TestR5DecimalMoney` |

**Residual note (R2):** the gate estimate is currency-agnostic (uses the catalog price as-is); aligning the estimate to the cap's currency is a refinement beyond this pass. The line-item pricing IS currency-correct (R4).

---

## 0. Verification of the 2026-06-01 remediation (all CONFIRMED closed)

| Finding | Status now | Evidence (current code) |
|---|---|---|
| **P1** quote-at-cost / inverted precedence | ✅ closed | `grep transfer_price\|supplier_price\|prices\[0\]` in `quote_service.py` → **none**. Pricing is `part_pricing.resolve_unit_price` (price-list → cost+margin → unpriced). |
| **P2/P3** dual matchers / unguarded `matches[0]` | ✅ closed | `quote_service._resolve_line_match` uses the resolver verdict first; `parts_matcher` fallback gated at `LINE_ITEM_MATCH_THRESHOLD=80`. |
| **Q1/Q2** spreadsheet qty heuristic / 10k cap | ✅ closed | `email_attachment_parser.extract_rows_as_parts` is header-aware; cap is `MAX_REASONABLE_QTY=1_000_000`. |
| **Q3** hyphen-variant double-count | ✅ closed | `_merge_heuristic_parts` dedups by `_normalize(code)`. |
| **Q5** no quantity bounds at line creation | ✅ closed | `_safe_quantity` bounds + flags. |
| **M1/M2** levenshtein neighbour / normalized collision | ✅ closed | `part_catalog_resolver`: digit-only full-code neighbour → `unknown`; collisions → `unknown` + logged. |

Both quote-from-email entry points — the **auto** path (`email_processing_service.py:777`) and the **operator-approved** API path (`quotes.py:259`) — go through the same fixed `create_quote_from_email`, so the pricing/matching fixes cover both. Good.

**But the re-audit found the remediation is not yet "perfect":** one of the original fixes (Q4) only *detects* the problem and nothing *enforces* it, and the surrounding hardening I added since introduced new exposure. Five findings below.

---

## 1. CRITICAL / HIGH — must fix for zero tolerance

### R1 — Quantity conflict is detected but **never enforced** (Q4 only half-closed)
- **Where:** flag set in `email_processing_service._merge_heuristic_parts:152-156` (`quantity_conflict` + `quantity_suspect`); **never read** by `_auto_quote_eligible` (`:32-93`) nor by `quote_service._create_items_with_matching`.
- **What's wrong:** when the body says "3" and the attachment says "10" for the same part, the merge records `quantity_conflict={"body":3,"attachment":10}` — then:
  1. `_auto_quote_eligible` doesn't look at it → the email still passes the gate and **auto-creates a draft quote**.
  2. `_create_items_with_matching` computes `quantity, qty_suspect = _safe_quantity(part_req.get("quantity"))` — it recomputes suspicion **only from the bounds check** (is the number 1..1e6), and ignores the upstream `quantity_suspect`/`quantity_conflict` keys. Since `3` is in-range, `qty_suspect=False` → the line is written with `quantity=3` and **`is_confirmed=True`**.
  3. `QuoteItem` has no conflict field, so the operator sees a confident line with no hint that the two sources disagreed.
- **Impact:** a body/attachment quantity disagreement silently auto-quotes one value as confirmed. Zero-tolerance violation — wrong quantity reaches a confirmed quote line.
- **Fix:** (a) `_auto_quote_eligible` returns `False, "quantity_conflict"` when any part carries `quantity_conflict`/`quantity_suspect`; (b) `_create_items_with_matching` forces `is_confirmed=False` when `part_req.get("quantity_suspect")` or `quantity_conflict` is present; (c) carry the conflict onto the line for the UI.

### R2 — The auto-quote **value cap (F-029) is a no-op for inbound email**
- **Where:** `_auto_quote_eligible:81-86` calls `estimate_quote_total(parsed)` (`tenant_settings_service.estimate_quote_total`), which sums `part["unit_price"] * quantity`.
- **What's wrong:** the Claude extraction tool (`claude_parser._EXTRACTION_TOOL`) extracts code/description/quantity/urgency — **never a price** (customers don't send prices in RFQs). So parsed parts have no `unit_price`; `estimate_quote_total` returns `0`; the `est > 0` guard is false; the cap is skipped on **every** inbound email.
- **Impact:** the control that's supposed to force human review on large orders ("big deals always require a human") never fires for the email pipeline. A 500k TRY RFQ of exact-match parts auto-quotes.
- **Fix:** estimate the total against the **catalog sell price** (resolve `catalog_part_id` → `resolve_unit_price`) at gate time, or move the cap check to *after* line pricing in `_auto_create_draft_quote` and reject/route-to-review when the priced total exceeds the cap.

---

## 2. MEDIUM

### R3 — Per-call input truncation cuts the **current email**, keeps stale thread history
- **Where:** `email_processing_service._parse_email_with_fallback` — `llm_input_body = prepend_thread_context(...)` returns `f"{thread_block}\n\n---\n\n# Current email\n\n{body}"` (`email_thread_context.py:16`), i.e. **thread history first, current email last**. The cap I added truncates `llm_input_body[:AI_MAX_INPUT_CHARS]` — the **tail** — so it discards the *current* email's attachment text while preserving older thread context.
- **What's wrong:** for non-tabular attachments (a prose PDF whose parts live in `text`, with no `rows` → empty `heuristic_parts`), parts beyond the cap are dropped. Tabular attachments are protected (heuristic_parts ride a separate path), but prose ones are not, and the ordering makes the *most* important content (this email) the first to be cut.
- **Fix:** truncate the **thread-context** block (least important) before the current email; or cap the two segments independently so the current email's body+attachments are always retained.

### R4 — Silent currency mixing in price selection
- **Where:** `part_pricing.select_price_entry:67-73`. When `preferred_currency` is set but **no** `PriceEntry` matches it, `matched` is empty and `valid` is left unchanged → it returns a foreign-currency entry.
- **What's wrong:** a TRY quote can be priced from a `net_price` denominated in USD (e.g. 250 USD written onto the line as 250 TRY) — a large, silent magnitude error.
- **Fix:** when no price exists in the quote's currency, return `unpriced` (force review) rather than a mismatched-currency price; or convert explicitly via a known FX rate and record it. For zero tolerance, prefer **unpriced + review**.

---

## 3. LOW

### R5 — Float money arithmetic
- **Where:** `SparePart.transfer_price/supplier_price`, `PriceEntry.list_price/net_price`, `Quote.*` are `Numeric(19,2, asdecimal=False)` → Python `float`. `quote_service` computes `line_total`, `subtotal`, `tax`, `grand_total` in float (rounded per step).
- **What's wrong:** float accumulation can drift at the cent level on large multi-line quotes. Per-line `round(...,2)` mitigates but doesn't eliminate it.
- **Fix:** compute monetary math in `Decimal` (the DB already stores 2-dp NUMERIC); convert at the boundary only.

---

## 4. What is genuinely solid (verified this pass)
- Pricing never quotes at/below cost; price-list-first; margin applied; unpriced → not auto-confirmed.
- Line-item SKU == the resolver verdict the gate evaluated; sub-threshold matcher results don't auto-populate SKU/price.
- Spreadsheet quantity is header-aware and bounds-checked; hyphen variants collapse to one line.
- Resolver refuses digit-only full-code neighbours and ambiguous normalized collisions.
- Strict auto-quote gate (auth=pass + every part exact/normalized + not first-time-sender + review APPROVED + AV-clean).
- AV-infected attachments are neutralized (text/parts cleared) and blocked from auto-quote.

---

## 5. Honest bottom line
The 2026-06-01 remediation closed every originally-scoped defect, and both quote paths are covered. It is **not yet "perfect"**: a detected **quantity conflict is not enforced** (R1) and the **large-order value cap doesn't fire** for email (R2) — both let a wrong-quantity or oversized quote auto-create as confirmed. Two medium issues (input-truncation order R3, currency mixing R4) and one low (float money R5) round out the gaps. R1 and R2 should be fixed before this feature is called zero-tolerance.

---

## 6. Remediation plan (test-first, ordered by risk)
1. **R1** — enforce quantity uncertainty: gate rejects `quantity_conflict`/`quantity_suspect`; line creation forces `is_confirmed=False` and carries the conflict; tests: conflict → not eligible + line unconfirmed.
2. **R2** — price-aware value cap: estimate from catalog sell price (or check post-pricing) so the per-tenant max-amount actually gates inbound RFQs; test: high-value exact-match RFQ → `value_above_threshold`.
3. **R4** — no cross-currency pricing: unpriced + review when the quote currency has no price entry; test: USD-only catalog price + TRY quote → unpriced.
4. **R3** — truncate thread context, not the current email; test: oversized thread + current-email part → current part retained.
5. **R5** — Decimal money math in `quote_service` totals; test: multi-line rounding equals Decimal expectation.

**Files of record:** `email_processing_service.py`, `quote_service.py`, `part_pricing.py`, `email_attachment_parser.py`, `tenant_settings_service.py`, `claude_parser.py`, `email_thread_context.py`; models `spare_part.py`, `price_entry.py`, `quote*.py`. Prior: `docs/audits/2026-06-01-spare-parts-extraction-audit.md`.
