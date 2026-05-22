"""Round-17 email attachment extraction & part-list parsing.

Closes the biggest hole in the email pipeline coverage audit
(docs/audits/2026-05-21-email-pipeline-coverage.md): inbound mails
carrying parts requests as Excel / CSV / PDF attachments were
**not parsed at all** — the IMAP poll fetched only ``text/plain``
and ``text/html`` body parts. A customer sending a 50-row Excel
RFQ disappeared into the void.

This module turns each supported attachment into a normalized
plain-text representation suitable for downstream Claude parsing
(``claude_parser.parse_email``). The representation preserves
tabular structure as markdown tables so the LLM can read off
``part_code | description | qty`` triples without column collapse.

Supported types (whitelist enforced — anything else is rejected):

* ``.xlsx`` / ``.xlsm`` / ``.xltx`` / ``.xltm`` via ``openpyxl``
* ``.xls`` (legacy) — opportunistic via openpyxl's older support
* ``.csv`` / ``.tsv`` via ``pandas`` + ``chardet`` encoding sniff
* ``.pdf`` via ``pdfplumber`` — preserves embedded tables when
  present, falls back to plain text extraction otherwise

Each parser is wrapped in a try/except guard. A single malformed
attachment never blocks the rest of the message: failures log a
warning and return an empty ``ParsedAttachment`` with the
``error`` field populated so the operator can triage in the
review queue.

Size + count limits (per ``settings.EMAIL_ATTACHMENT_*``):

* ``MAX_ATTACHMENT_BYTES``: 10 MiB per file (refuses larger)
* ``MAX_ATTACHMENTS_PER_MESSAGE``: 10 files
* ``MAX_TOTAL_ATTACHMENT_BYTES``: 25 MiB combined

Macros are deliberately ignored: ``openpyxl.load_workbook`` is
called with ``keep_vba=False`` and ``data_only=True`` so formula
results are read but macros / VBA payloads are stripped.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Whitelist + limits ────────────────────────────────────────────


SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".xlsx",
    ".xlsm",
    ".xltx",
    ".xltm",
    ".xls",
    ".csv",
    ".tsv",
    ".pdf",
    # Round-18 — image attachments routed to Claude Vision OCR.
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tiff",
    ".tif",
    ".webp",
    ".bmp",
})

# Image extensions handled separately via OCR rather than the
# text/table parsers below.
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tiff",
    ".tif",
    ".webp",
    ".bmp",
})

# Defaults — overridable via app.core.config.settings if/when those
# attributes land. Hard-coded here so the parser is usable
# stand-alone (e.g. from a CLI re-parse script).
DEFAULT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MiB
DEFAULT_MAX_ATTACHMENTS_PER_MESSAGE = 10
DEFAULT_MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MiB


@dataclass
class ParsedAttachment:
    """Normalized representation of one attachment.

    ``text`` is the extracted plain text (or markdown for tables).
    ``rows`` is the structured row form when the attachment was a
    table — useful for direct part-list extraction without an LLM
    round-trip. ``error`` is set when extraction failed; ``text``
    and ``rows`` are empty in that case.
    """

    filename: str
    content_type: str
    size_bytes: int
    text: str = ""
    rows: list[list[Any]] = field(default_factory=list)
    sheet_count: int = 0
    page_count: int = 0
    error: str | None = None


def _filename_ext(filename: str) -> str:
    """Return the lowercased extension including the leading dot."""
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def is_supported(filename: str) -> bool:
    """Quick check whether a filename's extension is on the whitelist."""
    return _filename_ext(filename) in SUPPORTED_EXTENSIONS


# ── Excel parser ──────────────────────────────────────────────────


def _parse_xlsx(data: bytes, filename: str) -> ParsedAttachment:
    """Extract text + structured rows from an Excel workbook.

    ``data_only=True`` resolves formulas to their last-saved values
    (we don't want to evaluate formulas server-side). ``keep_vba=
    False`` strips macros — any VBA payload is dropped before the
    bytes even enter our processing graph.
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        return ParsedAttachment(
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=len(data),
            error=f"openpyxl not installed: {exc}",
        )

    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(data),
            data_only=True,
            keep_vba=False,
            read_only=True,
        )
    except Exception as exc:  # noqa: BLE001 — bytestream may be malformed
        logger.warning("XLSX parse failed for %s: %s", filename, exc)
        return ParsedAttachment(
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=len(data),
            error=f"xlsx parse failed: {exc}",
        )

    sections: list[str] = []
    all_rows: list[list[Any]] = []
    sheet_count = 0
    for sheet in wb.worksheets:
        sheet_count += 1
        rows = [
            [cell if cell is not None else "" for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        # Drop fully empty trailing rows
        while rows and all(_cell_empty(c) for c in rows[-1]):
            rows.pop()
        if not rows:
            continue
        all_rows.extend(rows)
        sections.append(_rows_to_markdown(sheet.title, rows))

    wb.close()

    return ParsedAttachment(
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(data),
        text="\n\n".join(sections),
        rows=all_rows,
        sheet_count=sheet_count,
    )


def _cell_empty(cell: Any) -> bool:
    if cell is None:
        return True
    if isinstance(cell, str) and not cell.strip():
        return True
    return False


def _rows_to_markdown(sheet_name: str, rows: list[list[Any]]) -> str:
    """Render a 2D row list as a markdown table.

    Markdown is the most LLM-friendly tabular format: cell alignment
    is explicit, headers carry semantic weight, and Claude (and most
    other LLMs) recognize ``|`` separators in the prompt as a real
    table rather than wrapped prose.
    """
    if not rows:
        return f"## {sheet_name}\n_(empty)_"

    # First row → header; pad to widest row so column count is uniform.
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    header = norm[0]
    body = norm[1:] if len(norm) > 1 else []

    def _fmt(c: Any) -> str:
        if c is None:
            return ""
        s = str(c).strip()
        # Escape pipes so markdown rendering stays intact.
        return s.replace("|", "\\|")

    lines: list[str] = [f"## {sheet_name}", ""]
    lines.append("| " + " | ".join(_fmt(c) for c in header) + " |")
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in body:
        lines.append("| " + " | ".join(_fmt(c) for c in row) + " |")
    return "\n".join(lines)


# ── CSV / TSV parser ──────────────────────────────────────────────


def _parse_csv(data: bytes, filename: str, separator: str | None = None) -> ParsedAttachment:
    """Decode bytes (charset-aware), then parse with stdlib csv.

    chardet is used to sniff the encoding because CSVs from
    Turkish ERPs frequently arrive as ``windows-1254`` or
    ``iso-8859-9``. A wrong encoding produces "ÖZEL ÖL├╝" garbage
    that the LLM can't recover from.
    """
    ext = _filename_ext(filename)
    sep = separator or ("\t" if ext == ".tsv" else None)

    try:
        import chardet
        detected = chardet.detect(data) or {}
        encoding = detected.get("encoding") or "utf-8"
    except ImportError:  # pragma: no cover
        encoding = "utf-8"
    except Exception:  # noqa: BLE001
        encoding = "utf-8"

    try:
        text = data.decode(encoding, errors="replace")
    except LookupError:
        text = data.decode("utf-8", errors="replace")

    # If no explicit separator and not a .tsv, sniff with csv.Sniffer
    # on the first 4 KB.
    if sep is None:
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
            sep = dialect.delimiter
        except csv.Error:
            sep = ","

    rows: list[list[Any]] = []
    try:
        reader = csv.reader(io.StringIO(text), delimiter=sep)
        for row in reader:
            rows.append(list(row))
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSV parse failed for %s: %s", filename, exc)
        return ParsedAttachment(
            filename=filename,
            content_type="text/csv",
            size_bytes=len(data),
            error=f"csv parse failed: {exc}",
        )

    return ParsedAttachment(
        filename=filename,
        content_type="text/csv",
        size_bytes=len(data),
        text=_rows_to_markdown(filename, rows),
        rows=rows,
    )


# ── PDF parser ────────────────────────────────────────────────────


def _parse_pdf(data: bytes, filename: str) -> ParsedAttachment:
    """Extract text and tables from a PDF.

    pdfplumber's ``extract_tables()`` returns a list of row-lists
    when the page contains a detectable table grid. When no table
    is found we fall back to ``extract_text()`` and let Claude
    parse the prose. Pages are concatenated with form-feed-style
    headers so the LLM can tell where one page ends and the next
    begins.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        return ParsedAttachment(
            filename=filename,
            content_type="application/pdf",
            size_bytes=len(data),
            error=f"pdfplumber not installed: {exc}",
        )

    sections: list[str] = []
    all_rows: list[list[Any]] = []
    page_count = 0
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                page_count += 1
                tables = page.extract_tables() or []
                if tables:
                    for ti, table in enumerate(tables, start=1):
                        rows = [list(row) for row in (table or []) if row]
                        if not rows:
                            continue
                        all_rows.extend(rows)
                        sections.append(_rows_to_markdown(f"Page {idx} table {ti}", rows))
                else:
                    text = page.extract_text() or ""
                    if text.strip():
                        sections.append(f"## Page {idx}\n\n{text.strip()}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF parse failed for %s: %s", filename, exc)
        return ParsedAttachment(
            filename=filename,
            content_type="application/pdf",
            size_bytes=len(data),
            error=f"pdf parse failed: {exc}",
        )

    return ParsedAttachment(
        filename=filename,
        content_type="application/pdf",
        size_bytes=len(data),
        text="\n\n".join(sections),
        rows=all_rows,
        page_count=page_count,
    )


# ── Dispatcher ────────────────────────────────────────────────────


def parse_attachment(
    data: bytes,
    filename: str,
    *,
    max_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
) -> ParsedAttachment:
    """Dispatch to the right parser based on filename extension.

    Returns a ``ParsedAttachment`` with ``error`` set when:

      * the extension is not on the whitelist
      * the file exceeds ``max_bytes``
      * the underlying library raises

    None of the failure modes raise — the caller can safely loop
    over a message's attachments and collect parsed + failed
    results side by side.
    """
    ext = _filename_ext(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        return ParsedAttachment(
            filename=filename,
            content_type="application/octet-stream",
            size_bytes=len(data),
            error=f"unsupported extension: {ext or '(none)'}",
        )

    if len(data) > max_bytes:
        return ParsedAttachment(
            filename=filename,
            content_type="application/octet-stream",
            size_bytes=len(data),
            error=(
                f"attachment exceeds size limit "
                f"({len(data)} > {max_bytes} bytes)"
            ),
        )

    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return _parse_xlsx(data, filename)
    if ext in {".csv", ".tsv"}:
        return _parse_csv(data, filename)
    if ext == ".pdf":
        return _parse_pdf(data, filename)
    if ext in _IMAGE_EXTENSIONS:
        # Image parsing requires a Claude Vision round-trip (async).
        # ``parse_attachment`` is sync, so we return a placeholder
        # ParsedAttachment marked ``requires_ocr=True`` via the error
        # field; the async-aware caller (e.g. the email-processing
        # pipeline) detects this and triggers the OCR path.
        return ParsedAttachment(
            filename=filename,
            content_type=_image_content_type(ext),
            size_bytes=len(data),
            text="",
            rows=[],
            error="requires_ocr",
        )

    # Shouldn't reach here given the whitelist guard above, but stay
    # defensive against future extension-set edits.
    return ParsedAttachment(
        filename=filename,
        content_type="application/octet-stream",
        size_bytes=len(data),
        error=f"no parser registered for extension {ext}",
    )


def _image_content_type(ext: str) -> str:
    """RFC 2046 content-type for image extensions on the whitelist."""
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mapping.get(ext, "application/octet-stream")


def parse_attachments(
    attachments: list[tuple[str, bytes]],
    *,
    max_bytes_per: int = DEFAULT_MAX_ATTACHMENT_BYTES,
    max_count: int = DEFAULT_MAX_ATTACHMENTS_PER_MESSAGE,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[ParsedAttachment]:
    """Parse a list of ``(filename, bytes)`` tuples with global caps.

    The per-file cap (``max_bytes_per``) and total cap
    (``max_total_bytes``) protect both the parsing thread and the
    downstream LLM context window. Attachments beyond ``max_count``
    are dropped with an error stub so the operator sees them in the
    review queue.
    """
    out: list[ParsedAttachment] = []
    running_total = 0
    for idx, (filename, data) in enumerate(attachments):
        if idx >= max_count:
            out.append(
                ParsedAttachment(
                    filename=filename,
                    content_type="application/octet-stream",
                    size_bytes=len(data),
                    error=(
                        f"attachment dropped: count exceeded "
                        f"({idx + 1} > {max_count})"
                    ),
                )
            )
            continue
        if running_total + len(data) > max_total_bytes:
            out.append(
                ParsedAttachment(
                    filename=filename,
                    content_type="application/octet-stream",
                    size_bytes=len(data),
                    error=(
                        f"attachment dropped: total size cap reached "
                        f"({running_total + len(data)} > {max_total_bytes} bytes)"
                    ),
                )
            )
            continue
        running_total += len(data)
        out.append(parse_attachment(data, filename, max_bytes=max_bytes_per))
    return out


# ── Body merge helper ─────────────────────────────────────────────


def merge_for_llm(body_text: str, parsed_attachments: list[ParsedAttachment]) -> str:
    """Combine the email body and parsed attachments into one prompt
    payload for ``claude_parser.parse_email``.

    The body always comes first; each successfully-parsed attachment
    becomes a numbered section so the LLM can refer back to the
    source. Attachments that errored out are listed at the end with
    their error message — Claude is told "skip these but flag in
    confidence" by the system prompt.
    """
    parts: list[str] = []
    body_clean = (body_text or "").strip()
    if body_clean:
        parts.append("# Email body\n\n" + body_clean)
    else:
        parts.append("# Email body\n\n_(empty)_")

    ok = [a for a in parsed_attachments if a.error is None and a.text]
    failed = [a for a in parsed_attachments if a.error is not None]

    for i, a in enumerate(ok, start=1):
        parts.append(f"# Attachment {i}: {a.filename}\n\n{a.text}")

    if failed:
        parts.append("# Attachments not parsed")
        for a in failed:
            parts.append(f"- {a.filename} ({a.size_bytes} bytes): {a.error}")

    return "\n\n---\n\n".join(parts)


# ── Async OCR enrichment (Round-18) ───────────────────────────────


async def enrich_with_ocr(
    raw_attachments: list[tuple[str, bytes]],
    parsed: list[ParsedAttachment],
) -> list[ParsedAttachment]:
    """Run Claude Vision OCR on attachments that need it.

    Two pathways trigger OCR:

      1. **Image attachments** marked ``requires_ocr`` by the sync
         dispatcher (`parse_attachment`). The OCR text becomes the
         parsed attachment's ``text`` field; extracted parts become
         the ``rows`` payload that downstream
         ``extract_rows_as_parts`` consumes.

      2. **Scanned PDFs** where ``_parse_pdf`` returned no text or
         table content. We re-render those pages and OCR each.

    Returns a new list with the same ordering as ``parsed`` but
    with OCR-augmented entries replacing the placeholder rows.
    The raw_attachments tuple list is used to look up the original
    bytes by filename — the parsed list alone doesn't carry bytes.
    """
    if not parsed:
        return parsed

    # Index raw bytes by filename for the OCR lookups.
    by_name: dict[str, bytes] = {fn: data for fn, data in raw_attachments}

    out: list[ParsedAttachment] = []
    for pa in parsed:
        ext = _filename_ext(pa.filename)
        # Image path
        if ext in _IMAGE_EXTENSIONS and pa.error == "requires_ocr":
            data = by_name.get(pa.filename)
            if data is None:
                out.append(pa)
                continue
            try:
                from app.services.email_ocr import ocr_image_via_vision

                result = await ocr_image_via_vision(data, pa.filename)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OCR image failed for %s: %s", pa.filename, exc)
                out.append(
                    ParsedAttachment(
                        filename=pa.filename,
                        content_type=pa.content_type,
                        size_bytes=pa.size_bytes,
                        error=f"ocr_failed: {exc}",
                    )
                )
                continue
            if result.get("error"):
                out.append(
                    ParsedAttachment(
                        filename=pa.filename,
                        content_type=pa.content_type,
                        size_bytes=pa.size_bytes,
                        error=result["error"],
                    )
                )
                continue
            ocr_parts = result.get("parts") or []
            summary = result.get("page_summary") or ""
            text_blob = _ocr_result_to_markdown(pa.filename, summary, ocr_parts)
            out.append(
                ParsedAttachment(
                    filename=pa.filename,
                    content_type=pa.content_type,
                    size_bytes=pa.size_bytes,
                    text=text_blob,
                    rows=_ocr_parts_to_rows(ocr_parts),
                    page_count=1,
                )
            )
            continue

        # Scanned PDF path — pdfplumber returned empty text.
        if ext == ".pdf" and not pa.text and pa.error is None:
            data = by_name.get(pa.filename)
            if data is None:
                out.append(pa)
                continue
            try:
                from app.services.email_ocr import ocr_pdf_pages_via_vision

                result = await ocr_pdf_pages_via_vision(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OCR PDF failed for %s: %s", pa.filename, exc)
                out.append(pa)
                continue
            ocr_parts = result.get("parts") or []
            if not ocr_parts and not result.get("page_summary"):
                # Truly empty PDF — keep the placeholder.
                out.append(pa)
                continue
            text_blob = _ocr_result_to_markdown(
                pa.filename,
                result.get("page_summary") or "",
                ocr_parts,
            )
            out.append(
                ParsedAttachment(
                    filename=pa.filename,
                    content_type=pa.content_type,
                    size_bytes=pa.size_bytes,
                    text=text_blob,
                    rows=_ocr_parts_to_rows(ocr_parts),
                    page_count=result.get("page_count") or 0,
                )
            )
            continue

        out.append(pa)
    return out


def _ocr_result_to_markdown(
    filename: str,
    summary: str,
    parts: list[dict[str, Any]],
) -> str:
    """Render OCR output in the same markdown shape as text parsers."""
    lines: list[str] = [f"## {filename} (OCR)"]
    if summary:
        lines.append("")
        lines.append(summary)
    if parts:
        lines.append("")
        lines.append("| Code | Description | Qty |")
        lines.append("| --- | --- | --- |")
        for p in parts:
            code = (p.get("part_code") or "").replace("|", "\\|")
            desc = (p.get("part_description") or "").replace("|", "\\|")
            qty = p.get("quantity") or 1
            lines.append(f"| {code} | {desc} | {qty} |")
    return "\n".join(lines)


def _ocr_parts_to_rows(parts: list[dict[str, Any]]) -> list[list[Any]]:
    """Convert OCR ``parts`` payload to the ``rows`` shape so the
    existing ``extract_rows_as_parts`` heuristic + the
    ``email_processing_service`` heuristic-merge codepath both
    pick the rows up uniformly."""
    rows: list[list[Any]] = [["Code", "Description", "Qty"]]
    for p in parts:
        rows.append(
            [
                p.get("part_code") or "",
                p.get("part_description") or "",
                p.get("quantity") or 1,
            ]
        )
    return rows


# ── Direct part-row heuristic (no LLM) ────────────────────────────

# Honeywell part-code patterns repeated here in a slightly more
# permissive form for tabular data. The narrow regex in
# regex_fallback_parser.py is tuned for prose; in tables the surrounding
# context is the cell border, so we can be more lenient.
_TABULAR_PART_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9]{1,3}\d{3,8}[A-Z]?\d{0,4}|\d{5,8}-\d{2,4})\b",
    re.IGNORECASE,
)


def extract_rows_as_parts(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Heuristic part-row extraction from a 2D row list.

    Used as a sanity / coverage check alongside the LLM extraction:
    if the LLM returns 3 parts but the heuristic finds 50 in the
    same Excel, the result lands in the review queue. Conservative
    on column detection — we look for any cell matching the part
    code regex and treat its row as a candidate. Quantity / unit
    column is best-effort (number cell nearby).
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        part_code: str | None = None
        qty: int | None = None
        description: str = ""
        for cell in row:
            text = "" if cell is None else str(cell).strip()
            if not text:
                continue
            m = _TABULAR_PART_PATTERN.search(text)
            if m and part_code is None:
                part_code = m.group(1)
                continue
            # First plain integer ≤ 9999 is treated as quantity guess
            if qty is None and text.replace(".", "").replace(",", "").isdigit():
                try:
                    val = int(text.replace(",", "").replace(".", ""))
                    if 0 < val < 10_000:
                        qty = val
                        continue
                except ValueError:
                    pass
            if not description:
                description = text
        if part_code is not None:
            out.append(
                {
                    "part_code": part_code,
                    "part_description": description,
                    "quantity": qty or 1,
                }
            )
    return out
