from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

# Competitor URLs to monitor (product/news pages)
COMPETITOR_SOURCES = {
    "Siemens": [
        "https://new.siemens.com/global/en/products/automation.html",
    ],
    "ABB": [
        "https://new.abb.com/products/measurement-products",
    ],
    "Schneider": [
        "https://www.se.com/ww/en/work/campaign/industrial-automation.html",
    ],
    "Emerson": [
        "https://www.emerson.com/en-us/automation-solutions",
    ],
}

CONTENT_MAX_CHARS = 3000
WORD_COUNT_THRESHOLD = 50

PRODUCT_UPDATE_KEYWORDS = [
    "new product", "launch", "release", "yeni urun",
]
PRICING_KEYWORDS = ["price", "pricing", "cost", "fiyat"]
BUSINESS_UPDATE_KEYWORDS = [
    "acquisition", "merger", "partnership", "ortaklik",
]
CUSTOMER_WIN_KEYWORDS = [
    "case study", "success", "customer", "musteri",
]


async def crawl_competitor(competitor_name: str) -> list[dict]:
    """Crawl competitor URLs and extract relevant content.

    Returns list of {competitor, source_url, content, category, date}.
    Gracefully fails if crawl4ai is not available.
    """
    results: list[dict] = []
    urls = COMPETITOR_SOURCES.get(competitor_name, [])
    if not urls:
        return results

    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        logger.warning("crawl4ai not installed, skipping competitor crawling")
        return results

    try:
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                try:
                    result = await crawler.arun(
                        url=url,
                        word_count_threshold=WORD_COUNT_THRESHOLD,
                        bypass_cache=True,
                    )

                    if result.success and result.markdown:
                        content = result.markdown[:CONTENT_MAX_CHARS]
                        title = url
                        if result.metadata:
                            title = result.metadata.get("title", url)

                        results.append({
                            "competitor": competitor_name,
                            "source_url": url,
                            "content": content,
                            "category": _categorize_content(content),
                            "date": datetime.now(timezone.utc).isoformat(),
                            "title": title,
                        })

                        logger.info(
                            "Crawled %s: %s (%d chars)",
                            competitor_name, url, len(content),
                        )
                    else:
                        logger.warning("Failed to crawl %s: %s", competitor_name, url)

                except Exception as exc:
                    logger.warning(
                        "Crawl failed for %s %s: %s",
                        competitor_name, url, exc,
                    )
                    continue

    except Exception as exc:
        logger.error("Crawler initialization failed: %s", exc)

    return results


def _categorize_content(content: str) -> str:
    """Simple keyword-based categorization of crawled content."""
    content_lower = content.lower()

    if any(kw in content_lower for kw in PRODUCT_UPDATE_KEYWORDS):
        return "product_update"
    if any(kw in content_lower for kw in PRICING_KEYWORDS):
        return "pricing"
    if any(kw in content_lower for kw in BUSINESS_UPDATE_KEYWORDS):
        return "business_update"
    if any(kw in content_lower for kw in CUSTOMER_WIN_KEYWORDS):
        return "customer_win"
    return "general"


async def crawl_all_competitors() -> dict:
    """Crawl all known competitors and return results.

    Optionally stores in Qdrant if FEATURE_RAG is enabled.
    """
    all_results: list[dict] = []

    for competitor_name in COMPETITOR_SOURCES:
        try:
            results = await crawl_competitor(competitor_name)
            all_results.extend(results)

            if settings.FEATURE_RAG:
                try:
                    from app.services.vector_store import store_competitor_intel

                    for result in results:
                        await store_competitor_intel(result)
                except Exception as exc:
                    logger.warning("Failed to store in Qdrant: %s", exc)

        except Exception as exc:
            logger.warning("Failed to crawl %s: %s", competitor_name, exc)

    logger.info(
        "Competitor crawl complete: %d results from %d competitors",
        len(all_results), len(COMPETITOR_SOURCES),
    )
    return {"total_results": len(all_results), "results": all_results}
