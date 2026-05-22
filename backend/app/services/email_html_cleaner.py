"""HTML body cleaning + table-preserving text extraction for emails.

The Round-15 IMAP poll used a 3-line regex (``<style|script>`` strip,
then ``<[^>]+>`` removal) to convert HTML bodies to plain text. Two
problems with that approach:

1. **Tables collapse.** ``<table><tr><td>code</td><td>qty</td></tr>``
   becomes ``codeqty`` — column boundaries vanish before the LLM
   parser ever sees them. Customers who send RFQs as inline HTML
   tables (the second most common after Excel attachments) saw their
   part lists mangled.
2. **XSS surface.** Regex-based HTML stripping is known unreliable;
   anything that escapes the loose ``<[^>]+>`` pattern (``<svg
   onload=...>``, ``<img onerror=...>`` written across line breaks,
   etc.) survives into the stored body. The email detail page
   renders the body — anyone who reads a malicious mail would
   trigger the payload.

This module replaces the regex approach with two passes:

* ``sanitize_html(html)`` — Bleach with an allowlist that strips
  every tag *except* the ones we genuinely want to keep for
  display (links, lists, basic formatting). Removes ``<script>``,
  ``<style>``, event handlers, ``javascript:`` URLs, and embedded
  data URIs.
* ``html_to_text(html)`` — converts the sanitized HTML to a
  table-preserving plain text representation using lxml. Tables
  become markdown ``|``-pipe rows; everything else is normalized
  to text with paragraph breaks.

Both functions are total: they never raise on malformed HTML. A
parse error returns the input string with HTML tags stripped via
a conservative fallback regex.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Sanitization allowlist ────────────────────────────────────────


# Allowlist tuned for email bodies: enough formatting to keep the
# visual hierarchy (lists, links, simple emphasis, tables for RFQs)
# without giving HTML enough rope to execute. Every other tag is
# stripped to plain text content.
_BLEACH_ALLOWED_TAGS: list[str] = [
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "u",
    "ul",
    # Tables — RFQs frequently land as inline HTML tables.
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]

_BLEACH_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title"],
    # Allow basic column-span attributes so the lxml→markdown stage
    # can render merged headers reasonably.
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}

# Bleach's default protocols accept http / https / mailto / tel. We
# also accept ``cid:`` since IMAP messages reference inline images
# that way; the email detail page chooses whether to fetch them.
_BLEACH_ALLOWED_PROTOCOLS: list[str] = ["http", "https", "mailto", "tel", "cid"]


def sanitize_html(html: str) -> str:
    """Strip executable / event-binding / unknown HTML from a body.

    Returns the sanitized HTML on success. On failure (Bleach
    import error or unexpected runtime error) returns the
    aggressively-stripped fallback so the system stays open rather
    than refusing legitimate mail.
    """
    if not html:
        return ""
    try:
        import bleach
    except ImportError:  # pragma: no cover — installed via requirements
        return _fallback_strip(html)
    try:
        cleaned = bleach.clean(
            html,
            tags=_BLEACH_ALLOWED_TAGS,
            attributes=_BLEACH_ALLOWED_ATTRS,
            protocols=_BLEACH_ALLOWED_PROTOCOLS,
            strip=True,
            strip_comments=True,
        )
        return cleaned
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bleach sanitize failed: %s", exc)
        return _fallback_strip(html)


def _fallback_strip(html: str) -> str:
    """Conservative regex fallback when Bleach is unavailable.

    Mirrors the legacy ``emails.py`` regex but adds case-insensitive
    matching across newlines so multi-line ``<script>`` blocks don't
    survive.
    """
    s = re.sub(
        r"<(style|script)[^>]*>[\s\S]*?</\1>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


# ── HTML → text with table preservation ───────────────────────────


def html_to_text(html: str) -> str:
    """Convert HTML (already sanitized or not) to table-preserving text.

    Tables become markdown so downstream LLM parsing reads them as
    structured data, not a wall of run-together cell contents. Other
    block elements (paragraphs, list items, line breaks) are turned
    into newlines. Inline elements collapse to plain text.

    The function is total: any lxml error falls back to
    ``_fallback_strip``.
    """
    if not html or not html.strip():
        return ""
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover
        return _fallback_strip(html)

    try:
        root = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001 — lxml raises a broad family
        return _fallback_strip(html)

    out_lines: list[str] = []
    _emit_node(root, out_lines)
    text = "\n".join(out_lines)
    # Collapse 3+ blank lines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _emit_node(node: Any, out: list[str]) -> None:
    """Walk an lxml element tree, appending markdown-style lines to ``out``.

    Strategy: each element is responsible for its own output. Block
    elements emit a complete paragraph/markdown block then return —
    they do NOT recurse into children that would also emit (avoids
    duplicate emission of nested text). Inline / structural wrappers
    push their direct text and walk children one by one.
    """
    tag = (node.tag or "").lower() if isinstance(node.tag, str) else ""

    # Block elements — emit once, do not recurse further.
    if tag == "table":
        out.append(_table_to_markdown(node))
        out.append("")
        return
    if tag in {"ul", "ol"}:
        for i, li in enumerate(node.iterchildren("li"), start=1):
            prefix = "- " if tag == "ul" else f"{i}. "
            content = _text_content(li)
            if content:
                out.append(prefix + content)
        out.append("")
        return
    if tag in {"pre", "code"}:
        text = _text_content(node)
        if text:
            out.append(text)
        return

    # Paragraph-like blocks: emit own text, walk children for nested
    # tables only, then append trailing newline.
    is_paragraph_like = tag in {"p", "div", "section", "article", "blockquote"}
    if is_paragraph_like and out and out[-1] != "":
        out.append("")

    # Direct text (before any child) — strip but preserve a single
    # space between adjacent text runs at the same level.
    direct = (node.text or "").strip()
    if direct:
        out.append(direct)

    if tag == "br":
        out.append("")

    # Walk children. For each child, dispatch by tag — block elements
    # emit themselves and don't double-emit. Inline elements
    # contribute their text content here so we don't traverse them.
    for child in node:
        child_tag = (child.tag or "").lower() if isinstance(child.tag, str) else ""
        if child_tag in {"table", "ul", "ol", "p", "div", "section",
                          "article", "blockquote", "pre", "code"}:
            _emit_node(child, out)
        else:
            inline_text = _text_content(child)
            if inline_text:
                if out and out[-1] and not is_paragraph_like:
                    out[-1] = out[-1] + " " + inline_text
                else:
                    out.append(inline_text)
            if child_tag == "br":
                out.append("")
        tail = (child.tail or "").strip()
        if tail:
            if out and out[-1] and not is_paragraph_like and child_tag != "br":
                out[-1] = out[-1] + " " + tail
            else:
                out.append(tail)

    if is_paragraph_like:
        out.append("")


def _text_content(node: Any) -> str:
    """Return ``node`` and all descendants flattened to plain text."""
    try:
        text = node.text_content()
    except AttributeError:
        text = node.text or ""
    return " ".join((text or "").split())


def _table_to_markdown(table: Any) -> str:
    """Convert one ``<table>`` element to a markdown table string."""
    rows: list[list[str]] = []
    # th and td both work as cells.
    for tr in table.iter("tr"):
        cells = [_text_content(c) for c in tr.iter("th", "td")]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]

    def _fmt(c: str) -> str:
        return (c or "").replace("|", "\\|").strip()

    lines = []
    lines.append("| " + " | ".join(_fmt(c) for c in norm[0]) + " |")
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in norm[1:]:
        lines.append("| " + " | ".join(_fmt(c) for c in row) + " |")
    return "\n".join(lines)


# ── One-call helper ──────────────────────────────────────────────


def sanitize_and_extract_text(html: str) -> tuple[str, str]:
    """Sanitize HTML and return ``(safe_html, plain_text)``.

    The safe HTML is what the email detail page can render; the
    plain text is what the LLM parser consumes. Both are derived
    from the same sanitized intermediate so the two views can't
    drift (e.g. the LLM never sees a ``<script>`` the user's
    browser blocked but the parser didn't).
    """
    safe = sanitize_html(html)
    plain = html_to_text(safe)
    return safe, plain
