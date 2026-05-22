"""Round-17 email-attachment parser unit tests.

Covers:
  * .xlsx happy path → markdown table + heuristic part rows
  * .csv with TR encoding sniffing (windows-1254)
  * .pdf with embedded table extraction
  * whitelist rejects .exe / .zip / unknown extensions
  * per-file size cap
  * total-attachment size + count caps
  * malformed bytes don't raise — error field populated
  * merge_for_llm produces a single prompt body
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from app.services.email_attachment_parser import (
    extract_rows_as_parts,
    is_supported,
    merge_for_llm,
    parse_attachment,
    parse_attachments,
    ParsedAttachment,
)


# ── Helpers ───────────────────────────────────────────────────────


def _make_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFQ"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Whitelist ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("rfq.xlsx", True),
        ("RFQ.XLSX", True),
        ("parts.csv", True),
        ("parts.tsv", True),
        ("quote.pdf", True),
        ("evil.exe", False),
        ("payload.zip", False),
        ("noext", False),
        ("", False),
    ],
)
def test_is_supported(filename: str, expected: bool) -> None:
    assert is_supported(filename) is expected


# ── .xlsx parsing ─────────────────────────────────────────────────


def test_parse_xlsx_happy_path() -> None:
    data = _make_xlsx(
        [
            ["Honeywell Code", "Description", "Qty"],
            ["C7061A1012", "Flame detector", 5],
            ["RM7895A1014", "Burner controller", 2],
        ]
    )
    result = parse_attachment(data, "rfq.xlsx")
    assert result.error is None
    assert result.sheet_count == 1
    assert len(result.rows) == 3
    assert "C7061A1012" in result.text
    assert "Flame detector" in result.text
    assert "|" in result.text  # markdown table


def test_xlsx_heuristic_part_rows() -> None:
    data = _make_xlsx(
        [
            ["Code", "Desc", "Qty"],
            ["C7061A1012", "Flame detector", 5],
            ["RM7895A1014", "Burner controller", 2],
        ]
    )
    result = parse_attachment(data, "rfq.xlsx")
    parts = extract_rows_as_parts(result.rows)
    codes = {p["part_code"] for p in parts}
    assert codes == {"C7061A1012", "RM7895A1014"}
    by_code = {p["part_code"]: p for p in parts}
    assert by_code["C7061A1012"]["quantity"] == 5


def test_xlsx_macros_ignored() -> None:
    """``keep_vba=False`` is passed — even .xlsm shouldn't execute macros.

    We can't easily simulate a malicious macro in-test, but we can
    verify the loader doesn't choke on a workbook saved with
    ``data_only=True`` semantics (formula cells return last-saved
    values, not the formula).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "=1+1"  # formula
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    result = parse_attachment(data, "calc.xlsx")
    assert result.error is None


# ── .csv parsing + charset ────────────────────────────────────────


def test_parse_csv_utf8() -> None:
    csv = "part,desc,qty\nC7061A1012,Flame detector,5\n".encode("utf-8")
    result = parse_attachment(csv, "rfq.csv")
    assert result.error is None
    assert len(result.rows) == 2  # header + 1 row


def test_parse_csv_windows_1254() -> None:
    """Turkish CSV exports from older ERPs use windows-1254 — must
    not produce garbage."""
    csv = "kod,açıklama,adet\nC7061A1012,Şahin algılayıcı,3\n".encode("windows-1254")
    result = parse_attachment(csv, "rfq.csv")
    assert result.error is None
    text = result.text
    assert "Şahin" in text or "ahin algılayıcı" in text  # chardet may pick latin-5/iso-8859-9


def test_parse_csv_semicolon_separator() -> None:
    csv = b"part;desc;qty\nC7061A1012;Flame detector;5\n"
    result = parse_attachment(csv, "rfq.csv")
    assert result.error is None
    assert any("C7061A1012" in str(c) for r in result.rows for c in r)


# ── .pdf parsing ──────────────────────────────────────────────────


def test_parse_pdf_text_only() -> None:
    """Build a minimal PDF with reportlab if available; else skip."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "C7061A1012 — Flame detector x 5")
    c.drawString(72, 700, "RM7895A1014 — Burner controller x 2")
    c.save()
    data = buf.getvalue()

    result = parse_attachment(data, "rfq.pdf")
    assert result.error is None
    assert result.page_count >= 1
    assert "C7061A1012" in result.text


# ── Rejection paths ───────────────────────────────────────────────


def test_unsupported_extension_rejected() -> None:
    result = parse_attachment(b"\x4D\x5A\x90\x00", "malware.exe")
    assert result.error is not None
    assert "unsupported" in result.error


def test_per_file_size_cap() -> None:
    data = b"x" * 2048
    result = parse_attachment(data, "rfq.xlsx", max_bytes=1024)
    assert result.error is not None
    assert "size limit" in result.error


def test_malformed_xlsx_does_not_raise() -> None:
    """Random bytes should not throw — error field populated."""
    result = parse_attachment(b"not actually an xlsx", "rfq.xlsx")
    assert result.error is not None
    assert "xlsx parse failed" in result.error


def test_batch_count_cap() -> None:
    """Exceeding ``max_count`` drops extras with an error entry."""
    attachments = [
        ("rfq.xlsx", _make_xlsx([["a"], ["b"]])) for _ in range(3)
    ]
    results = parse_attachments(attachments, max_count=2)
    assert len(results) == 3
    assert results[0].error is None
    assert results[1].error is None
    assert results[2].error is not None
    assert "count exceeded" in results[2].error


def test_batch_total_size_cap() -> None:
    big = _make_xlsx([["x"] for _ in range(1000)])
    attachments = [("big1.xlsx", big), ("big2.xlsx", big)]
    results = parse_attachments(
        attachments,
        max_bytes_per=10 * 1024 * 1024,
        max_total_bytes=len(big),
    )
    assert results[0].error is None
    assert results[1].error is not None
    assert "total size cap" in results[1].error


# ── merge_for_llm ─────────────────────────────────────────────────


def test_merge_for_llm_body_plus_attachments() -> None:
    body = "Merhaba, ekteki listeden parça istiyorum."
    pa = ParsedAttachment(
        filename="rfq.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=1234,
        text="## RFQ\n| Code | Qty |\n| --- | --- |\n| C7061A1012 | 5 |",
    )
    blob = merge_for_llm(body, [pa])
    assert "Email body" in blob
    assert "Merhaba" in blob
    assert "Attachment 1: rfq.xlsx" in blob
    assert "C7061A1012" in blob


def test_merge_for_llm_with_failed_attachment() -> None:
    body = ""
    failed = ParsedAttachment(
        filename="evil.exe",
        content_type="application/octet-stream",
        size_bytes=100,
        error="unsupported extension: .exe",
    )
    blob = merge_for_llm(body, [failed])
    assert "Attachments not parsed" in blob
    assert "evil.exe" in blob
    assert "unsupported" in blob
