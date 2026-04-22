"""AI-powered email parsing using Anthropic Claude API with tool-use pattern."""

import asyncio
import hashlib
import logging
from collections import OrderedDict

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.services.ai_trust import AITrustContext, audit_record, scrub, unscrub

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 5000

# LRU cache: OrderedDict gives O(1) move-to-end on access
_parse_cache: OrderedDict[str, dict] = OrderedDict()

# Cache hit/miss counters for observability
_cache_hits = 0
_cache_misses = 0

# Tool definition for structured extraction
_EXTRACTION_TOOL = {
    "name": "extract_email_data",
    "description": (
        "Extract structured data from a customer email. "
        "Always extract ALL part numbers and descriptions found in the email, "
        "even if mentioned informally or embedded in sentences. "
        "If no specific part code is found but a part is described, use an empty "
        "string for part_code and fill in part_description."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["tr", "en", "de", "fr", "other"],
                "description": "Detected language of the email.",
            },
            "customer_name": {
                "type": "string",
                "description": (
                    "Full name of the person sending the email. "
                    "Look in signature lines, 'From:', or greeting closings. "
                    "Return empty string if not identifiable."
                ),
            },
            "customer_company": {
                "type": "string",
                "description": (
                    "Company name of the sender. Look in signature, "
                    "email domain, or explicit mentions. "
                    "Return empty string if not identifiable."
                ),
            },
            "parts": {
                "type": "array",
                "description": (
                    "List of ALL requested parts or items. Include every part "
                    "mentioned, even without explicit part codes. "
                    "Common Honeywell part code formats: C7061A1012, "
                    "RM7895A1014, R7847A1033, 51309276-150, ST3000."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "part_code": {
                            "type": "string",
                            "description": (
                                "Part number/code (e.g., 'C7061A1012'). "
                                "Empty string if no code is mentioned."
                            ),
                        },
                        "part_description": {
                            "type": "string",
                            "description": (
                                "Description of the part as mentioned by the customer. "
                                "Include the original wording."
                            ),
                        },
                        "quantity": {
                            "type": "integer",
                            "description": (
                                "Requested quantity. Default to 1 if not "
                                "explicitly specified."
                            ),
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["low", "normal", "high", "critical"],
                            "description": (
                                "Urgency: 'critical' if words like acil/urgent/"
                                "asap; 'high' if soon/hemen; 'normal' default; "
                                "'low' if no rush mentioned."
                            ),
                        },
                    },
                    "required": [
                        "part_code",
                        "part_description",
                        "quantity",
                        "urgency",
                    ],
                },
            },
            "is_spare_part_request": {
                "type": "boolean",
                "description": (
                    "True if the email requests spare parts, pricing for parts, "
                    "or mentions specific part numbers."
                ),
            },
            "category": {
                "type": "string",
                "enum": [
                    "spare_part_request",
                    "price_inquiry",
                    "complaint",
                    "order_status",
                    "technical_support",
                    "general_inquiry",
                ],
                "description": (
                    "Primary category of this email. "
                    "'spare_part_request' if ordering/requesting parts. "
                    "'price_inquiry' if asking for quotation/pricing. "
                    "'complaint' if reporting a problem/defect. "
                    "'order_status' if asking about delivery/shipment. "
                    "'technical_support' if asking for technical help. "
                    "'general_inquiry' for everything else."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Confidence score 0.0-1.0 for overall parsing accuracy. "
                    "Lower if email is ambiguous or poorly formatted."
                ),
            },
        },
        "required": [
            "language",
            "customer_name",
            "customer_company",
            "parts",
            "is_spare_part_request",
            "category",
            "confidence",
        ],
    },
}

_SYSTEM_PROMPT = """\
You are an expert email parser for a Honeywell spare parts sales team in Turkey.
Your job is to extract ALL structured information from customer emails accurately.

CRITICAL RULES:
1. Extract EVERY part number mentioned, even if embedded in sentences or tables.
2. Honeywell part codes follow patterns like: C7061A1012, RM7895A1014, \
R7847A1033, 51309276-150, ST3000, ML7984A4009.
3. If a customer describes a part without a code (e.g., "flame detector" or \
"alev dedektoru"), still include it with an empty part_code.
4. Quantities may appear as "X adet", "X pcs", "X pieces", "qty: X", or \
simply a number before/after the part code.
5. Look for urgency clues: "acil", "urgent", "asap", "hemen", "kritik" = \
critical/high. Default is "normal".
6. Customer name and company are often in the email signature (last lines).
7. Emails may be in Turkish, English, or mixed.

EXAMPLES:

Email: "Merhaba, asagidaki parcalara ihtiyacimiz var:\\n\
C7061A1012 - 2 adet\\nRM7895A1014 - 1 adet\\nAcil gonderim gerekiyor.\\n\
Saygilarimla, Ahmet Yilmaz\\nABC Endustriyel"
-> parts: [{part_code: "C7061A1012", quantity: 2, urgency: "critical"}, \
{part_code: "RM7895A1014", quantity: 1, urgency: "critical"}]
-> customer_name: "Ahmet Yilmaz", customer_company: "ABC Endustriyel"

Email: "Hi, we need a flame detector for our boiler system. Please send quote."
-> parts: [{part_code: "", part_description: "flame detector for boiler system", \
quantity: 1, urgency: "normal"}]
-> category: "price_inquiry"

Email: "Siparis 12345 ne zaman teslim edilecek?"
-> parts: [], category: "order_status"

Always use the extract_email_data tool to return results.\
"""

MAX_RETRIES = 3
BASE_BACKOFF = 1.0


async def parse_email(body: str, subject: str = "") -> dict:
    """Parse email using Claude API with tool-use pattern.

    Returns a dict with keys: language, customer_name, customer_company,
    parts, is_spare_part_request, category, confidence.

    Uses SHA256 caching and retries with exponential backoff.
    """
    global _cache_hits, _cache_misses

    cache_key = hashlib.sha256(f"{subject}||{body}".encode()).hexdigest()
    if cache_key in _parse_cache:
        _cache_hits += 1
        _parse_cache.move_to_end(cache_key)
        if _cache_hits % 100 == 0:
            total = _cache_hits + _cache_misses
            rate = _cache_hits / total * 100 if total else 0
            logger.info(
                "Parse cache: %d hits, %d misses (%.1f%% hit rate)",
                _cache_hits,
                _cache_misses,
                rate,
            )
        return _parse_cache[cache_key]
    _cache_misses += 1

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set; returning empty parse result")
        return _empty_result()

    logger.info("Claude parsing initiated")

    client = AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=30.0,
    )
    model = settings.AI_MODEL_NAME
    max_tokens = settings.AI_MAX_TOKENS
    raw_message = f"Subject: {subject}\n\n{body}" if subject else body

    trust_enabled = bool(settings.FEATURE_AI_TRUST_LAYER)
    trust_ctx: AITrustContext | None = None
    if trust_enabled:
        user_message, trust_ctx = scrub(raw_message)
        if trust_ctx.is_dirty():
            logger.info(
                "ai_trust.scrubbed hits=%s model=%s",
                trust_ctx.totals(),
                model,
            )
    else:
        user_message = raw_message

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_SYSTEM_PROMPT,
                tools=[_EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_email_data"},
                messages=[{"role": "user", "content": user_message}],
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "extract_email_data":
                    result = block.input
                    # Restore any masked PII in string fields before downstream use.
                    if trust_ctx is not None and trust_ctx.is_dirty():
                        result = _unscrub_result(result, trust_ctx)
                        logger.info(
                            "ai_trust.audit %s",
                            audit_record(trust_ctx, prompt=raw_message, model=model),
                        )
                    if result.get("parts"):
                        _parse_cache[cache_key] = result
                        if len(_parse_cache) > MAX_CACHE_SIZE:
                            _parse_cache.popitem(last=False)
                    logger.info(
                        "Parsed email: category=%s, parts=%d, confidence=%.2f",
                        result.get("category"),
                        len(result.get("parts", [])),
                        result.get("confidence", 0),
                    )
                    return result
                elif block.type == "tool_use":
                    logger.warning("Unexpected tool_use: %s", block.name)

            logger.warning(
                "No tool_use block in response. Stop reason: %s",
                response.stop_reason,
            )
            return _empty_result()

        except Exception as exc:
            last_error = exc
            wait = BASE_BACKOFF * (2 ** attempt)
            logger.warning(
                "Claude API attempt %d/%d failed: %s. Retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                exc,
                wait,
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(wait)

    logger.error("All %d Claude API attempts failed: %s", MAX_RETRIES, last_error)
    raise ClaudeApiError(f"All {MAX_RETRIES} attempts failed: {last_error}")


class ClaudeApiError(Exception):
    """Raised when all Claude API retry attempts are exhausted."""


def _unscrub_result(result: dict, trust_ctx: AITrustContext) -> dict:
    """Recursively restore masked PII tokens in Claude's structured output.

    Only string leaves are touched so numeric scores / booleans pass through.
    """

    def walk(value):
        if isinstance(value, str):
            return unscrub(value, trust_ctx)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    return walk(result)


def _empty_result() -> dict:
    return {
        "language": "tr",
        "customer_name": "",
        "customer_company": "",
        "parts": [],
        "is_spare_part_request": False,
        "category": "general_inquiry",
        "confidence": 0.0,
    }


def clear_cache() -> None:
    """Clear the parse cache (useful for testing)."""
    _parse_cache.clear()
