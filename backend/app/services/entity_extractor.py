"""Named Entity Recognition for customer linking.

Uses xlm-roberta-base NER model to extract person and organization names
from email text, then fuzzy-matches against the customers table.
"""

import logging
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_ner_pipeline = None
MODEL_NAME = "Davlan/xlm-roberta-base-ner-hrl"


def _get_pipeline():
    """Lazy-load the NER pipeline."""
    global _ner_pipeline
    if _ner_pipeline is not None:
        return _ner_pipeline

    try:
        import os
        os.environ.setdefault("TRANSFORMERS_CACHE", "data/models")
        from transformers import pipeline
        _ner_pipeline = pipeline(
            "ner",
            model=MODEL_NAME,
            aggregation_strategy="simple",
        )
        logger.info("Loaded NER model: %s", MODEL_NAME)
        return _ner_pipeline
    except Exception as e:
        logger.warning("Failed to load NER model: %s", e)
        return None


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract person and organization entities from text.

    Returns {"persons": [...], "organizations": [...]}
    """
    pipe = _get_pipeline()
    if pipe is None:
        return {"persons": [], "organizations": []}

    try:
        # Truncate long texts
        truncated = text[:1000] if len(text) > 1000 else text
        results = pipe(truncated)

        persons = []
        organizations = []

        for entity in results:
            label = entity.get("entity_group", "")
            word = entity.get("word", "").strip()
            score = entity.get("score", 0)

            if score < 0.5 or len(word) < 2:
                continue

            if label == "PER":
                persons.append(word)
            elif label == "ORG":
                organizations.append(word)

        # Deduplicate
        persons = list(dict.fromkeys(persons))
        organizations = list(dict.fromkeys(organizations))

        return {"persons": persons, "organizations": organizations}

    except Exception as e:
        logger.warning("NER extraction failed: %s", e)
        return {"persons": [], "organizations": []}


async def link_to_customer(
    db: AsyncSession, entities: dict[str, list[str]]
) -> dict[str, Any] | None:
    """Try to match extracted entities to existing customers.

    Returns matched customer dict or None.
    """
    from app.models.customer import Customer

    all_names = entities.get("persons", []) + entities.get("organizations", [])
    if not all_names:
        return None

    result = await db.execute(select(Customer))
    customers = result.scalars().all()

    if not customers:
        return None

    best_match = None
    best_score = 0

    for name in all_names:
        for customer in customers:
            # Match against name and company
            name_score = fuzz.token_set_ratio(name.lower(), (customer.name or "").lower())
            company_score = fuzz.token_set_ratio(name.lower(), (customer.company or "").lower())
            score = max(name_score, company_score)

            if score > best_score and score >= 70:
                best_score = score
                best_match = {
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "customer_company": customer.company,
                    "matched_entity": name,
                    "match_score": score,
                }

    return best_match
