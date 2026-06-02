"""Per-call LLM input-size cap tests (token-budget protection).

A large attachment (e.g. a spreadsheet rendered to markdown) must not
blow the per-call token budget. ``merge_for_llm`` caps each attachment's
text; structured part rows are unaffected because they ride the separate
``heuristic_parts`` path, not the prompt text.
"""

from __future__ import annotations

from app.services.email_attachment_parser import ParsedAttachment, merge_for_llm


def _att(text: str, filename: str = "rfq.xlsx") -> ParsedAttachment:
    return ParsedAttachment(
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(text),
        text=text,
    )


class TestAttachmentTextCap:
    def test_long_attachment_truncated_to_cap(self):
        big = "C7061A1012 " * 5000  # ~55k chars
        blob = merge_for_llm("see attached", [_att(big)], max_attachment_chars=8000)
        assert "truncated for length" in blob
        # the attachment section is bounded near the cap (+ body + markers)
        assert len(blob) < 8000 + 2000

    def test_no_cap_keeps_full_text(self):
        big = "C7061A1012 " * 1000
        blob = merge_for_llm("body", [_att(big)], max_attachment_chars=None)
        assert "truncated for length" not in blob
        assert big.strip() in blob

    def test_short_attachment_not_truncated(self):
        blob = merge_for_llm("body", [_att("C7061A1012")], max_attachment_chars=8000)
        assert "truncated for length" not in blob
        assert "C7061A1012" in blob

    def test_body_always_present_even_when_attachment_capped(self):
        blob = merge_for_llm(
            "URGENT please quote", [_att("x" * 20000)], max_attachment_chars=500
        )
        assert "URGENT please quote" in blob
        assert "truncated for length" in blob
