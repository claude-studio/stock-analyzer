"""뉴스 헤드라인 배치 감성 분석."""

import asyncio
import json
import re
from decimal import Decimal

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.claude_runner import ClaudeRunner
from app.database.models import NewsArticle

logger = structlog.get_logger(__name__)

SENTIMENT_PROMPT = """다음 금융 뉴스 헤드라인들을 분석해주세요.

각 헤드라인에 대해 (1) 감성, (2) 직접 영향을 받는 종목/섹터를 분석하세요.
JSON 배열로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

형식:
[
  {"index": 0, "sentiment": "positive", "score": 0.85, "tickers": ["005930"], "names": ["삼성전자"], "sector": "반도체", "impact": "1분기 실적 호조로 주가 상승 기대"},
  {"index": 1, "sentiment": "negative", "score": 0.72, "tickers": [], "names": ["카카오"], "sector": "플랫폼", "impact": "규제 강화로 수익성 악화 우려"},
  ...
]

규칙:
- sentiment: "positive", "negative", "neutral" 중 하나
- score: 해당 감성의 확신도 (0.0~1.0)
- tickers: 직접 언급되거나 영향 받는 종목코드 (없으면 빈 배열)
- names: 직접 언급되거나 영향 받는 종목명 (없으면 빈 배열)
- sector: 관련 섹터 (없으면 빈 문자열)
- impact: 해당 뉴스가 주식시장에 미치는 영향 한 줄 요약 (없으면 빈 문자열)

헤드라인 목록:
"""


def _extract_json_array_from_text(text: str) -> list[dict] | None:
    """raw 텍스트에서 JSON 배열을 추출 시도한다."""
    # ```json ... ``` 블록 추출
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 첫 번째 [ ... ] 블록 추출
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def analyze_sentiment_batch(
    runner: ClaudeRunner,
    headlines: list[str],
    batch_size: int = 20,
) -> list[dict]:
    """뉴스 헤드라인 배치 감성 분석.

    Returns:
        [{"index": int, "sentiment": str, "score": float}, ...]
    """
    if not headlines:
        return []

    results: list[dict] = []

    for batch_start in range(0, len(headlines), batch_size):
        batch = headlines[batch_start : batch_start + batch_size]

        numbered = "\n".join(
            f"{i}. {headline}" for i, headline in enumerate(batch)
        )
        prompt = SENTIMENT_PROMPT + numbered

        try:
            raw = await runner.run(prompt, output_format="json")

            parsed: list[dict] | None = None
            if isinstance(raw, list):
                parsed = raw
            elif isinstance(raw, str):
                parsed = _extract_json_array_from_text(raw)

            if parsed is None:
                logger.warning(
                    "sentiment_batch_parse_failed",
                    batch_start=batch_start,
                    batch_size=len(batch),
                )
                continue

            # index를 전체 기준으로 보정 + score 정규화
            for item in parsed:
                item["index"] = item["index"] + batch_start
                raw_score = item.get("score", 0.0)
                label = item.get("sentiment", "neutral")
                if label == "negative":
                    item["score"] = -abs(raw_score)
                elif label == "neutral":
                    item["score"] = 0.0
                # positive는 양수 그대로 유지

            results.extend(parsed)

            logger.info(
                "sentiment_batch_done",
                batch_start=batch_start,
                batch_size=len(batch),
                parsed_count=len(parsed),
            )

        except (TimeoutError, RuntimeError) as e:
            logger.warning(
                "sentiment_batch_failed",
                batch_start=batch_start,
                batch_size=len(batch),
                error=str(e),
            )

        # 마지막 배치가 아니면 rate limit 방어 대기
        if batch_start + batch_size < len(headlines):
            await asyncio.sleep(1)

    return results


async def update_news_sentiment(
    session: AsyncSession,
    article_ids: list[int],
    sentiments: list[dict],
) -> int:
    """감성 분석 결과를 NewsArticle에 업데이트.

    Returns:
        업데이트된 행 수
    """
    if not article_ids or not sentiments:
        return 0

    updated = 0
    mappings: list[dict] = []

    for i, sentiment in enumerate(sentiments):
        if i >= len(article_ids):
            break

        idx = sentiment.get("index", i)
        if idx >= len(article_ids):
            logger.warning("sentiment_index_out_of_range", index=idx, total=len(article_ids))
            continue

        score = sentiment.get("score", 0.0)
        label = sentiment.get("sentiment", "neutral")

        mappings.append({
            "article_id": article_ids[idx],
            "score": Decimal(str(round(score, 3))),
            "label": label,
        })

    if not mappings:
        return 0

    for mapping in mappings:
        stmt = (
            update(NewsArticle)
            .where(NewsArticle.id == mapping["article_id"])
            .values(
                sentiment_score=mapping["score"],
                sentiment_label=mapping["label"],
            )
        )
        result = await session.execute(stmt)
        updated += result.rowcount

    await session.flush()

    logger.info("news_sentiment_updated", updated_count=updated, total=len(mappings))

    return updated
