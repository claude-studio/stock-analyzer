"""RSS 뉴스 수집기 (httpx + feedparser)."""

import asyncio
from datetime import UTC, datetime

import feedparser
import httpx
import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES_PER_FEED = 20
SUMMARY_MAX_LENGTH = 500
REQUEST_TIMEOUT = 15.0

KR_FINANCE_RSS: dict[str, str] = {
    "연합인포맥스": "https://news.einfomax.co.kr/rss/allArticle.xml",
    "한국경제": "https://www.hankyung.com/feed/finance",
    "매일경제": "https://www.mk.co.kr/rss/40300001/",
    "이데일리": "https://rss.edaily.co.kr/edaily/stock.xml",
}


def _parse_feed(source: str, raw_content: str) -> list[dict]:
    """feedparser로 RSS 원문을 파싱하여 뉴스 항목 리스트를 반환한다."""
    feed = feedparser.parse(raw_content)
    entries = feed.entries[:MAX_ENTRIES_PER_FEED]
    collected_at = datetime.now(tz=UTC).isoformat()
    results = []
    for entry in entries:
        summary_raw = entry.get("summary", "") or ""
        results.append(
            {
                "source": source,
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": summary_raw[:SUMMARY_MAX_LENGTH],
                "collected_at": collected_at,
            }
        )
    return results


async def _fetch_and_parse(
    client: httpx.AsyncClient, source: str, url: str
) -> list[dict]:
    """단일 RSS 피드를 비동기로 가져와 파싱한다."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "rss_fetch_http_error",
            source=source,
            url=url,
            status_code=exc.response.status_code,
        )
        return []
    except httpx.RequestError as exc:
        logger.warning(
            "rss_fetch_request_error",
            source=source,
            url=url,
            error=str(exc),
        )
        return []

    parsed = await asyncio.to_thread(_parse_feed, source, response.text)
    logger.info("rss_feed_parsed", source=source, count=len(parsed))
    return parsed


async def collect_rss_news(
    feeds: dict[str, str] | None = None,
) -> list[dict]:
    """RSS 뉴스를 비동기로 수집한다.

    Args:
        feeds: {소스명: RSS URL} 딕셔너리. None이면 KR_FINANCE_RSS 사용.

    Returns:
        수집된 뉴스 항목 리스트. 각 항목은 source, title, link,
        published, summary(500자 제한), collected_at 키를 포함.
    """
    if feeds is None:
        feeds = KR_FINANCE_RSS

    logger.info("rss_collection_start", feed_count=len(feeds))
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_and_parse(client, source, url)
            for source, url in feeds.items()
        ]
        results = await asyncio.gather(*tasks)

    all_news = [item for feed_items in results for item in feed_items]
    logger.info("rss_collection_complete", total=len(all_news))
    return all_news
