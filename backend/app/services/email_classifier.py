"""Email classification with zero-shot neural model + keyword fallback + sentiment.

Primary: HuggingFace zero-shot classification (multilingual, no training needed)
Fallback: Keyword-based classification (if model unavailable)
Bonus: Turkish/multilingual sentiment analysis
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Zero-shot classifier ──
_zero_shot_pipeline = None
_sentiment_pipeline = None

CLASSIFIER_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
SENTIMENT_MODEL = "savasy/bert-base-turkish-sentiment-cased"

CATEGORY_LABELS = {
    "spare_part_request": "spare part request, yedek parça talebi, part order",
    "price_inquiry": "price inquiry, fiyat teklifi, quotation request",
    "complaint": "complaint, şikayet, dissatisfaction, problem report",
    "order_status": "order status, delivery tracking, sipariş durumu",
    "technical_support": "technical support, maintenance, arıza, bakım",
    "general_inquiry": "general inquiry, bilgi talebi, question",
}


def _get_zero_shot():
    """Lazy-load zero-shot classification pipeline."""
    global _zero_shot_pipeline
    if _zero_shot_pipeline is not None:
        return _zero_shot_pipeline

    try:
        os.environ.setdefault("TRANSFORMERS_CACHE", "data/models")
        from transformers import pipeline
        _zero_shot_pipeline = pipeline(
            "zero-shot-classification",
            model=CLASSIFIER_MODEL,
        )
        logger.info("Loaded zero-shot classifier: %s", CLASSIFIER_MODEL)
        return _zero_shot_pipeline
    except Exception as e:
        logger.warning("Failed to load zero-shot classifier: %s. Using keyword fallback.", e)
        return None


def _get_sentiment():
    """Lazy-load sentiment analysis pipeline."""
    global _sentiment_pipeline
    if _sentiment_pipeline is not None:
        return _sentiment_pipeline

    try:
        os.environ.setdefault("TRANSFORMERS_CACHE", "data/models")
        from transformers import pipeline
        _sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model=SENTIMENT_MODEL,
        )
        logger.info("Loaded sentiment model: %s", SENTIMENT_MODEL)
        return _sentiment_pipeline
    except Exception as e:
        logger.warning("Failed to load sentiment model: %s", e)
        return None


def classify_email(subject: str, body: str) -> dict:
    """Classify email category, confidence, price sensitivity, and sentiment.

    Tries zero-shot neural classification first, falls back to keywords.

    Returns:
        {
            "category": str,
            "confidence": float,
            "price_sensitivity": bool,
            "sentiment": str | None,       # "positive", "negative", "neutral"
            "sentiment_score": float | None,
            "method": str,                  # "neural" or "keyword"
        }
    """
    text = f"{subject or ''} {body or ''}".strip()
    if not text:
        return {
            "category": "general_inquiry",
            "confidence": 0.3,
            "price_sensitivity": False,
            "sentiment": None,
            "sentiment_score": None,
            "method": "keyword",
        }

    # ── Try neural classification ──
    category, confidence, method = _classify_neural(text)
    if category is None:
        category, confidence = _classify_keyword(text)
        method = "keyword"

    # ── Price sensitivity ──
    price_sensitivity = _check_price_sensitivity(text.lower())

    # ── Sentiment ──
    sentiment, sentiment_score = _analyze_sentiment(text)

    return {
        "category": category,
        "confidence": confidence,
        "price_sensitivity": price_sensitivity,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "method": method,
    }


def _classify_neural(text: str) -> tuple[str | None, float, str]:
    """Zero-shot classification with HuggingFace model."""
    pipe = _get_zero_shot()
    if pipe is None:
        return None, 0.0, "keyword"

    try:
        truncated = text[:512]
        candidate_labels = list(CATEGORY_LABELS.values())

        result = pipe(truncated, candidate_labels, multi_label=False)

        # Map back to category key
        label_to_key = {v: k for k, v in CATEGORY_LABELS.items()}
        top_label = result["labels"][0]
        top_score = result["scores"][0]

        category = label_to_key.get(top_label, "general_inquiry")
        confidence = round(float(top_score), 2)

        return category, confidence, "neural"

    except Exception as e:
        logger.warning("Neural classification failed: %s", e)
        return None, 0.0, "keyword"


def _analyze_sentiment(text: str) -> tuple[str | None, float | None]:
    """Analyze text sentiment (positive/negative/neutral)."""
    pipe = _get_sentiment()
    if pipe is None:
        return None, None

    try:
        truncated = text[:512]
        result = pipe(truncated)[0]
        label = result["label"].lower()
        score = round(float(result["score"]), 2)

        # Normalize label names
        if "positive" in label or "olumlu" in label:
            return "positive", score
        elif "negative" in label or "olumsuz" in label:
            return "negative", score
        else:
            return "neutral", score

    except Exception as e:
        logger.warning("Sentiment analysis failed: %s", e)
        return None, None


# ── Keyword fallback (unchanged from original) ──

_CATEGORY_KEYWORDS: list[tuple[str, list[str], float]] = [
    (
        "spare_part_request",
        [
            "yedek parça", "yedek parca", "spare part", "spare parts",
            "part number", "parça numarası", "parca numarasi",
            "parça kodu", "parca kodu", "part code",
        ],
        1.0,
    ),
    (
        "price_inquiry",
        [
            "teklif", "fiyat", "price", "quotation", "quote",
            "birim fiyat", "unit price", "pricing", "fiyat listesi",
            "price list", "proforma", "maliyet", "cost",
        ],
        0.9,
    ),
    (
        "complaint",
        [
            "şikayet", "sikayet", "complaint", "memnuniyetsizlik",
            "sorun", "problem", "issue", "arızalı", "arizali",
            "defective", "faulty", "hasarlı", "hasarli", "damaged",
        ],
        0.85,
    ),
    (
        "order_status",
        [
            "sipariş", "siparis", "order", "teslimat", "delivery",
            "kargo", "shipment", "tracking", "takip", "durum",
            "status", "ne zaman", "when", "eta",
        ],
        0.8,
    ),
    (
        "technical_support",
        [
            "teknik destek", "technical support", "arıza", "ariza",
            "bakım", "bakim", "maintenance", "calibration",
            "kalibrasyon", "kurulum", "installation", "commissioning",
            "devreye alma", "error code", "hata kodu",
        ],
        0.8,
    ),
    (
        "general_inquiry",
        [
            "bilgi", "information", "soru", "question", "inquiry",
            "hakkında", "about", "details", "detay",
        ],
        0.5,
    ),
]

_PRICE_SENSITIVITY_KEYWORDS: list[str] = [
    "bütçe", "butce", "budget", "indirim", "discount",
    "rakip", "competitor", "pahalı", "pahali", "expensive",
    "uygun fiyat", "affordable", "maliyet düşürme", "cost reduction",
    "alternatif", "alternative",
]


def _classify_keyword(text: str) -> tuple[str, float]:
    """Keyword-based classification (fallback)."""
    text_lower = re.sub(r"\s+", " ", text.lower())

    scores: dict[str, float] = {}
    for category, keywords, weight in _CATEGORY_KEYWORDS:
        match_count = sum(1 for kw in keywords if kw in text_lower)
        if match_count > 0:
            raw_score = (match_count / len(keywords)) * weight
            scores[category] = min(raw_score + (0.1 * match_count), 1.0)

    if scores:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best, round(min(scores[best], 1.0), 2)

    return "general_inquiry", 0.3


def _check_price_sensitivity(text_lower: str) -> bool:
    return any(kw in text_lower for kw in _PRICE_SENSITIVITY_KEYWORDS)
