# Email pipeline hardening — Round-17 (2026-05-22)

## Background

Pre-Round-17 coverage audit (informal, 2026-05-22) graded the email
pipeline at **~%45** with these specific gaps:

| Gap | Pre-Round-17 status |
|---|---|
| Excel attachment parsing | %0 — `walk()` ignored `application/*` parts |
| CSV attachment parsing | %0 — same |
| PDF attachment parsing | %0 — same |
| HTML table preservation in bodies | %20 — regex `<[^>]+>` removal collapsed columns |
| HTML XSS sanitization | %30 — regex strip, no bleach |
| Inbound SPF/DKIM/DMARC verification | %0 — `From:` header trusted verbatim |
| TLS cert verification on IMAP | %50 — `IMAP4_SSL` defaults, no explicit context |
| Part-code catalog cross-check | %0 — LLM output used as-is |
| Auto-quote eligibility gate | partial — only `review_status` checked |
| Test coverage for above | ~%25 |

## What this round shipped

### P0 — bleeding holes (closed)

1. **`app/services/email_attachment_parser.py`** — new module.
   * Whitelist: `.xlsx / .xlsm / .xltx / .xltm / .xls / .csv / .tsv / .pdf`
   * Per-file 10 MiB cap, 10-file count cap, 25 MiB total cap.
   * Excel via `openpyxl` with `keep_vba=False` + `data_only=True` —
     macros stripped at parse time.
   * CSV via stdlib `csv` + `chardet` charset sniffing (Turkish ERPs
     ship `windows-1254` files; pre-Round-17 those produced mojibake).
   * PDF via `pdfplumber` with `extract_tables()` first, prose
     fallback when no table grid is detected.
   * Tabular output rendered as markdown so the LLM sees explicit
     column boundaries.
   * `extract_rows_as_parts()` heuristic extracts part-code rows
     without an LLM round-trip — used as a sanity check alongside
     Claude's output.
   * `merge_for_llm(body, parsed_attachments)` builds the single
     prompt blob fed to Claude.

2. **`app/services/email_html_cleaner.py`** — new module.
   * `sanitize_html()` runs `bleach` with a tight allowlist (no
     `<script>`, `<style>`, event handlers, `javascript:` URIs,
     `data:` URIs).
   * `html_to_text()` uses `lxml` to preserve `<table>` as markdown
     tables in the plain-text projection. Tables, lists, paragraphs
     all map to their LLM-friendly markdown equivalent.
   * `sanitize_and_extract_text()` is the one-call helper returning
     `(safe_html, plain_text)` — guarantees the two views can't drift.

3. **IMAP fetch path (`api/v1/emails.py:_imap_fetch_emails`)** — extended.
   * `walk()` now collects `application/...` parts as attachments
     (filename via RFC 2047-aware `decode_header`).
   * `body_html` → `sanitize_and_extract_text` so the stored HTML is
     safe to render and the LLM input has table structure.
   * Per-message size + count caps enforced via
     `parse_attachments()`.

4. **Attachment whitelist + size caps** — implemented in
   `parse_attachment` / `parse_attachments` (defaults: 10 MiB / file,
   25 MiB / message, 10 files / message). Refused files surface in
   the email's review queue with a descriptive error string.

### P1 — security real (closed)

5. **SPF / DKIM / DMARC verification**
   (`app/services/email_auth_verifier.py`).
   * Reads the `Authentication-Results` header (added upstream by
     Google Workspace / Microsoft 365 / customer's MX).
   * Verdict ladder: `pass` (DMARC pass or SPF+DKIM both pass) /
     `fail` / `none` / `unverified`.
   * Uses the `authheaders` library when installed; conservative
     regex fallback otherwise.
   * Verdict persisted as `email_requests.sender_auth_status`.
   * Non-`pass` senders auto-route to review queue at IMAP ingest.

6. **TLS cert verification explicit on IMAP**
   (`api/v1/emails.py`):
   ```python
   ssl_ctx = ssl.create_default_context()
   ssl_ctx.check_hostname = True
   ssl_ctx.verify_mode = ssl.CERT_REQUIRED
   imap = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_ctx, timeout=30)
   ```
   Previously the default constructor was used — same behavior on
   modern Python but the explicit context lets future cert pinning
   land in one place.

### P2 — context enrichment (partial closure)

7. **Catalog cross-check + fuzzy match**
   (`app/services/part_catalog_resolver.py`).
   * Resolution ladder: `exact` → `normalized` (strip
     whitespace/hyphens) → `fuzzy_prefix` (unique prefix) →
     `fuzzy_levenshtein` (edit distance ≤ 2, unique winner) →
     `unknown`.
   * Damerau-Levenshtein (OSA variant) with cap-based early
     termination.
   * Every parsed part is annotated in-place with
     `catalog_status`, `canonical_part_code`, `catalog_part_id`,
     `catalog_edit_distance`.
   * The auto-quote gate (`_auto_quote_eligible`) now refuses
     anything except `exact` / `normalized`; fuzzy matches go to
     review even when the LLM was 100% confident.

8. **Heuristic-merge of attachment rows into LLM result**
   (`app/services/email_processing_service.py:_merge_heuristic_parts`).
   * If the LLM misses parts that the openpyxl heuristic found
     (e.g. an Excel column without a "code" header), those rows
     are appended to `parsed.parts` with `urgency="normal"` so the
     auto-quote path still sees them.
   * Deduplicates by `part_code` (case-insensitive); LLM entry
     wins on conflict.

## Database changes

```
alembic/versions/20260615_email_attachments_sender_auth.py
  - ADD COLUMN email_requests.attachments_json TEXT
  - ADD COLUMN email_requests.sender_auth_status VARCHAR(20)
```

Both nullable; legacy rows have no payload to backfill.

## Test coverage added

| Module | Tests | Notes |
|---|---|---|
| `test_email_attachment_parser.py` | 21 | xlsx happy / TR encoding CSV / malformed bytes / whitelist / size caps / batch caps |
| `test_email_html_cleaner.py` | 14 | XSS surface (script/style/event/JS URI/data URI) + table preservation + malformed input |
| `test_email_auth_verifier.py` | 10 | DMARC pass/fail / SPF+DKIM / softfail / multi-line header / empty bytes |
| `test_part_catalog_resolver.py` | 14 | every ladder rung + Damerau-Levenshtein edge cases |
| `test_email_pipeline_integration.py` | 11 | end-to-end JSON round-trip + auto-quote gate combinations |
| **Total new** | **70** | (+ 1 skipped — `reportlab` optional) |

All 70 pass locally on the PostgreSQL test DB.

## Updated coverage estimate

| Dimension | Pre-Round-17 | Post-Round-17 |
|---|---|---|
| Security overall | %55 | %85 |
| Parsing — text | %85 | %88 |
| Parsing — HTML table | %20 | %85 |
| Parsing — Excel / CSV | %0 | %90 |
| Parsing — PDF | %0 | %75 (text + tables; OCR still TODO) |
| Context | %40 | %65 |
| Test coverage | %25 | %75 |
| **Weighted total** | **~%45** | **~%80** |

## What remains (Round-18 candidates)

* **OCR for scanned PDFs / image attachments.** pdfplumber returns
  empty text on image-only PDFs. Tesseract or Anthropic Vision
  would close the last %20 of PDF coverage.
* **Inbound AV scan.** ClamAV daemon or VirusTotal API hash query
  before persisting attachment bytes.
* **Fernet key rotation.** `data/.encryption_key` is single-key
  today; a version field + env-var fallback would let ops rotate
  without re-encrypting every stored credential.
* **Thread-aware context injection.** Same `thread_id` history into
  the Claude prompt so a follow-up "yes also add 2 more of X"
  resolves "X" against the previous RFQ.
* **Multi-email RFQ aggregation.** Aggregate parts requested in
  the same thread within 7 days into a single RFQ.
* **Golden-file corpus for eval harness.** 50+ anonymized real
  emails (TR / EN, plain / HTML / Excel / PDF) — drives the
  recall / precision metric on every parser change.

— end Round-17 email pipeline hardening notes
