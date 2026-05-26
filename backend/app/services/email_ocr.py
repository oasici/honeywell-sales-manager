"""Round-18 OCR via Claude Vision for scanned PDFs and image attachments.

Round-17 closed the **text-bearing** attachment gap (Excel / CSV /
text-PDF), but two real-world cases still produced empty parse
results:

  1. **Scanned PDF RFQs.** Customers scan a paper RFQ form and
     send the PDF. ``pdfplumber.extract_text()`` returns empty
     because the bytes are an embedded image, not selectable text.
  2. **Image attachments.** Phone photo of a hand-written part
     list, screenshot of a competitor catalog page, etc. Pre-Round-18
     these were rejected by the whitelist.

This module solves both with Claude Vision:

* ``ocr_pdf_pages_via_vision(data)`` — renders any page whose text
  extraction failed as a PNG and sends it to Claude with the same
  structured-tool prompt used for text emails. Returns combined
  text suitable for downstream ``claude_parser`` merge.
* ``ocr_image_via_vision(data, content_type)`` — for direct image
  attachments. Same tool schema.

The Claude Vision call is gated by the existing circuit breaker
(``claude_messages_create``). A failure (breaker open or upstream
500) returns an empty result with the error captured — the rest of
the attachment pipeline still ships what it can.

Cost note: each image costs ≈ 1500 input tokens (an A4 page at
default resolution). The pipeline only calls Vision when the cheap
text-extraction path returned empty, so we don't pay per page when
the PDF was already text-bearing.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from app.core.claude_client import claude_messages_create
from app.core.config import settings

logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tiff",
    ".tif",
    ".webp",
    ".bmp",
})


_VISION_TOOL = {
    "name": "extract_parts_from_image",
    "description": (
        "Look at the page or image and extract every spare part / "
        "RFQ row visible. Common Honeywell part codes look like "
        "C7061A1012, RM7895A1014, 51309276-150, ST3000, ML7984A4009. "
        "Even if a row only has a description (e.g. \"flame "
        "detector\") with no code, still include it with an empty "
        "part_code. Quantities may be after the code (\"× 5\", \"5 "
        "adet\", \"5 pcs\")."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "part_code": {"type": "string"},
                        "part_description": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["part_code", "part_description", "quantity"],
                },
            },
            "page_summary": {
                "type": "string",
                "description": (
                    "One-paragraph summary of what the page contains: "
                    "RFQ form, scanned email, photo of part shelf, "
                    "etc. Helps the operator triage in the review queue."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "0.0-1.0 overall confidence in the extraction.",
            },
        },
        "required": ["parts", "page_summary", "confidence"],
    },
}


_VISION_SYSTEM = (
    "You are an expert at reading scanned RFQ forms, hand-written "
    "part lists, and photos of equipment for a Honeywell spare-parts "
    "sales team in Turkey. Extract every part number, description, "
    "and quantity you can see. Be conservative: it is better to "
    "return an empty list than to invent codes. Always call the "
    "extract_parts_from_image tool — never reply with prose."
)


_MEDIA_TYPE_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    # Anthropic supports PNG/JPEG/GIF/WEBP natively. TIFF and BMP
    # are converted to PNG before sending (handled in caller).
    ".tiff": "image/png",
    ".tif": "image/png",
    ".bmp": "image/png",
}


def _filename_ext(filename: str) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def is_image(filename: str) -> bool:
    """Whitelist check for image attachments."""
    return _filename_ext(filename) in IMAGE_EXTENSIONS


async def ocr_image_via_vision(
    data: bytes,
    filename: str,
) -> dict[str, Any]:
    """Send a single image to Claude Vision and return the parsed
    parts result.

    Returns a dict with keys ``parts`` (list), ``page_summary``
    (str), ``confidence`` (float), ``error`` (str | None). Failures
    are non-fatal — the caller can mark the attachment as
    `error` populated and move on.
    """
    if not settings.ANTHROPIC_API_KEY:
        return _empty_result(error="ANTHROPIC_API_KEY not set")

    ext = _filename_ext(filename)
    media_type = _MEDIA_TYPE_BY_EXT.get(ext)
    if media_type is None:
        return _empty_result(error=f"unsupported image extension: {ext}")

    image_bytes = data
    if ext in {".tiff", ".tif", ".bmp"}:
        image_bytes = _convert_to_png(data)
        if image_bytes is None:
            return _empty_result(error="image conversion failed")

    return await _call_vision(image_bytes, media_type, filename)


async def ocr_pdf_pages_via_vision(
    data: bytes,
    max_pages: int = 5,
) -> dict[str, Any]:
    """Render PDF pages as PNGs and OCR each via Claude Vision.

    Only runs when the upstream ``pdfplumber.extract_text()``
    returned empty — there is no point paying for Vision on a
    text-bearing PDF. Caps at ``max_pages`` to keep the per-message
    cost bounded; the remainder lands in the review queue with a
    "truncated to N pages" note so the operator can re-trigger.
    """
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return _empty_result(error="pdfplumber not installed")

    pages_rendered: list[bytes] = []
    total_pages: int = 0
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            total_pages = len(pdf.pages)
            for idx, page in enumerate(pdf.pages):
                if idx >= max_pages:
                    break
                # pdfplumber wraps pdfminer + can render via pypdfium2;
                # the underlying ``page.to_image()`` returns an
                # ``PIL.Image`` we can serialize as PNG.
                try:
                    img = page.to_image(resolution=150)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    pages_rendered.append(buf.getvalue())
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "PDF page render failed at idx=%d: %s", idx, exc
                    )
                    continue
    except Exception as exc:  # noqa: BLE001
        return _empty_result(error=f"pdf open failed: {exc}")

    if not pages_rendered:
        return _empty_result(error="no pages rendered")

    # OCR each page, accumulate parts, average confidence.
    all_parts: list[dict[str, Any]] = []
    summaries: list[str] = []
    confidences: list[float] = []
    any_error: str | None = None
    for idx, png_bytes in enumerate(pages_rendered):
        page_result = await _call_vision(png_bytes, "image/png", f"page_{idx + 1}")
        if page_result.get("error"):
            any_error = page_result["error"]
            continue
        for p in page_result.get("parts", []):
            all_parts.append(p)
        if page_result.get("page_summary"):
            summaries.append(f"p{idx + 1}: {page_result['page_summary']}")
        if isinstance(page_result.get("confidence"), (int, float)):
            confidences.append(float(page_result["confidence"]))

    rendered = len(pages_rendered)
    # F-003 — truncation marker. ``page_count`` was previously "how many
    # pages we OCR'd"; downstream couldn't tell the original was longer.
    # We now surface both values so the eligibility gate can refuse
    # auto-quote on incomplete OCR.
    return {
        "parts": all_parts,
        "page_summary": " | ".join(summaries) if summaries else "",
        "confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
        "page_count": rendered,
        "total_pages": total_pages,
        "truncated": total_pages > rendered,
        "error": any_error if not all_parts else None,
    }


async def _call_vision(
    image_bytes: bytes,
    media_type: str,
    label: str,
) -> dict[str, Any]:
    """Single Vision API call. Wraps the breaker-protected client."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    user_content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            },
        },
        {
            "type": "text",
            "text": (
                f"Image label: {label}. Extract parts via the "
                "extract_parts_from_image tool."
            ),
        },
    ]
    try:
        response = await claude_messages_create(
            timeout=45.0,
            model=settings.AI_MODEL_NAME,
            max_tokens=settings.AI_MAX_TOKENS,
            system=_VISION_SYSTEM,
            tools=[_VISION_TOOL],
            tool_choice={"type": "tool", "name": "extract_parts_from_image"},
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Claude Vision call failed for %s: %s", label, exc)
        return _empty_result(error=f"vision call failed: {exc}")

    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == "extract_parts_from_image":
            payload = getattr(block, "input", {}) or {}
            return {
                "parts": list(payload.get("parts") or []),
                "page_summary": payload.get("page_summary") or "",
                "confidence": float(payload.get("confidence") or 0.0),
                "error": None,
            }
    return _empty_result(error="no tool_use block in vision response")


def _convert_to_png(data: bytes) -> bytes | None:
    """Convert TIFF/BMP to PNG via Pillow.

    Returns None on failure so the caller can mark the attachment
    as `error` and keep parsing the rest of the message.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    try:
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image conversion failed: %s", exc)
        return None


def _empty_result(*, error: str | None = None) -> dict[str, Any]:
    return {
        "parts": [],
        "page_summary": "",
        "confidence": 0.0,
        "error": error,
    }
