"""AI-powered email parsing using Anthropic Claude API with tool-use pattern."""

import asyncio
import hashlib
import json
import logging

from anthropic import AsyncAnthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory cache (SHA256 hash -> parse result)
# Only cache successful results (with parts)
_parse_cache: dict[str, dict] = {}

# Tool definition for structured extraction
_EXTRACTION_TOOL = {
    "name": "extract_email_data",
    "description": (
        "Extract structured data from a customer email requesting spare parts or services. "
        "Identify the language, customer info, requested parts, and classify the request."
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
                "description": "Name of the person sending the email, if identifiable.",
            },
            "customer_company": {
                "type": "string",
                "description": "Company name of the sender, if identifiable.",
            },
            "parts": {
                "type": "array",
                "description": "List of requested parts or items.",
                "items": {
                    "type": "object",
                    "properties": {
                        "part_code": {
                            "type": "string",
                            "description": "Part number / code mentioned (e.g., 'C7061A1012').",
                        },
                        "part_description": {
                            "type": "string",
                            "description": "Description or name of the part as mentioned by the customer.",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Requested quantity. Default 1 if not specified.",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["low", "normal", "high", "critical"],
                            "description": "Urgency level based on context.",
                        },
                    },
                    "required": ["part_code", "part_description", "quantity", "urgency"],
                },
            },
            "is_spare_part_request": {
                "type": "boolean",
                "description": "True if the email is requesting spare parts or pricing for parts.",
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
                "description": "Category of the email request.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score from 0.0 to 1.0 for the overall parsing accuracy.",
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

_SYSTEM_PROMPT = (
    "You are an email parser for a Honeywell spare parts sales team in Turkey. "
    "Analyze the customer email and extract all structured information. "
    "The emails may be in Turkish or English. "
    "Look for part numbers (e.g., C7061A1012, RM7895A1014), quantities, "
    "and any urgency indicators. "
    "Use the extract_email_data tool to return structured results."
)

MAX_RETRIES = 3
BASE_BACKOFF = 1.0


async def parse_email(body: str, subject: str = "") -> dict:
    """Parse email using Claude API with tool-use pattern.

    Returns a dict with keys: language, customer_name, customer_company,
    parts, is_spare_part_request, category, confidence.

    Uses SHA256 caching and retries with exponential backoff.
    """
    # Build cache key
    cache_key = hashlib.sha256(f"{subject}||{body}".encode()).hexdigest()
    if cache_key in _parse_cache:
        logger.debug("Cache hit for email parse: %s", cache_key[:12])
        return _parse_cache[cache_key]

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set; returning empty parse result")
        return _empty_result()

    logger.info("Claude parsing with key: %s...", settings.ANTHROPIC_API_KEY[:10])

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_message = f"Subject: {subject}\n\n{body}" if subject else body

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=[_EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_email_data"},
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract the tool use block
            logger.info("Claude response blocks: %s", [b.type for b in response.content])
            for block in response.content:
                if block.type == "tool_use" and block.name == "extract_email_data":
                    result = block.input
                    # Only cache if we got actual parts
                    if result.get("parts"):
                        _parse_cache[cache_key] = result
                    logger.info(
                        "Parsed email: category=%s, parts=%d, confidence=%.2f",
                        result.get("category"),
                        len(result.get("parts", [])),
                        result.get("confidence", 0),
                    )
                    return result
                elif block.type == "tool_use":
                    logger.warning("Unexpected tool_use: %s", block.name)
                elif block.type == "text":
                    logger.info("Claude text response: %s", block.text[:200])

            logger.warning("No tool_use block found in Claude response. Stop reason: %s", response.stop_reason)
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
    return _empty_result()


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
