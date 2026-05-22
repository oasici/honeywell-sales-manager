"""Round-17 HTML cleaner unit tests.

Covers:
  * sanitize_html strips <script>, <style>, event handlers, javascript: URLs
  * sanitize_html keeps formatting (a, ul, ol, p, b, em, strong)
  * html_to_text preserves tables as markdown
  * malformed HTML doesn't raise
  * sanitize_and_extract_text returns (safe_html, plain_text) tuple
"""

from __future__ import annotations

from app.services.email_html_cleaner import (
    html_to_text,
    sanitize_and_extract_text,
    sanitize_html,
)


# ── Sanitization (XSS surface) ────────────────────────────────────


def test_strips_script_tag() -> None:
    html = "<p>ok</p><script>alert(1)</script>"
    out = sanitize_html(html)
    assert "script" not in out.lower()


def test_strips_style_tag() -> None:
    html = "<p>ok</p><style>p{color:red}</style>"
    out = sanitize_html(html)
    assert "<style" not in out.lower()


def test_strips_event_handlers() -> None:
    html = '<img src="x" onerror="alert(1)">'
    out = sanitize_html(html)
    assert "onerror" not in out.lower()


def test_strips_javascript_uri() -> None:
    html = '<a href="javascript:alert(1)">link</a>'
    out = sanitize_html(html)
    assert "javascript:" not in out.lower()


def test_strips_data_uri_script() -> None:
    html = '<a href="data:text/html,<script>alert(1)</script>">link</a>'
    out = sanitize_html(html)
    assert "javascript:" not in out.lower()
    assert "<script" not in out.lower()


def test_preserves_safe_formatting() -> None:
    html = '<p>Hello <b>world</b></p><ul><li>item</li></ul>'
    out = sanitize_html(html)
    assert "<p>" in out
    assert "<b>" in out
    assert "<ul>" in out
    assert "<li>" in out


def test_preserves_mailto_link() -> None:
    html = '<a href="mailto:foo@bar.com">contact</a>'
    out = sanitize_html(html)
    assert "mailto:" in out.lower()


# ── Table preservation in html_to_text ────────────────────────────


def test_table_becomes_markdown() -> None:
    html = """
    <table>
      <tr><th>Code</th><th>Qty</th></tr>
      <tr><td>C7061A1012</td><td>5</td></tr>
      <tr><td>RM7895A1014</td><td>2</td></tr>
    </table>
    """
    text = html_to_text(html)
    assert "C7061A1012" in text
    # Markdown table delimiter
    assert "|" in text
    assert "---" in text


def test_nested_table_inside_paragraph() -> None:
    html = """
    <p>Aşağıdaki parçaları istiyoruz:</p>
    <table>
      <tr><td>C7061A1012</td><td>5</td></tr>
    </table>
    <p>Saygılarımla</p>
    """
    text = html_to_text(html)
    assert "istiyoruz" in text
    assert "C7061A1012" in text
    assert "Saygılarımla" in text


def test_list_becomes_markdown_bullets() -> None:
    html = "<ul><li>first</li><li>second</li></ul>"
    text = html_to_text(html)
    assert "- first" in text
    assert "- second" in text


def test_ordered_list_numbered() -> None:
    html = "<ol><li>a</li><li>b</li></ol>"
    text = html_to_text(html)
    assert "1. a" in text
    assert "2. b" in text


# ── Resilience ────────────────────────────────────────────────────


def test_malformed_html_does_not_raise() -> None:
    text = html_to_text("<p>unclosed <span>no end <p>second")
    assert isinstance(text, str)


def test_empty_input() -> None:
    assert sanitize_html("") == ""
    assert html_to_text("") == ""


def test_one_call_helper() -> None:
    html = "<p>Hi <script>alert(1)</script></p>"
    safe, plain = sanitize_and_extract_text(html)
    assert "script" not in safe.lower()
    assert "Hi" in plain
