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
- news_category: "earnings", "policy", "macro", "sector", "supply_demand", "rumor", "general" 중 하나

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

            # index를 전체 기준으로 보정 + score 정규화 + 누락 필드 기본값
            for item in parsed:
                item["index"] = item["index"] + batch_start
                raw_score = item.get("score", 0.0)
                label = item.get("sentiment", "neutral")
                if label == "negative":
                    item["score"] = -abs(raw_score)
                elif label == "neutral":
                    item["score"] = 0.0
                # positive는 양수 그대로 유지

                item.setdefault("tickers", [])
                item.setdefault("names", [])
                item.setdefault("sector", "")
                item.setdefault("impact", "")
                item.setdefault("news_category", "general")

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
    stock_name_map: dict[str, int] | None = None,
) -> int:
    """감성 분석 결과를 NewsArticle에 업데이트.

    Args:
        session: DB 세션
        article_ids: 뉴스 기사 ID 목록
        sentiments: 감성 분석 결과 목록
        stock_name_map: 종목명->id 매핑 (LLM 종목 매칭 + NewsStockImpact 생성용)

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
        news_category = sentiment.get("news_category", "general")
        impact_text = sentiment.get("impact", "")
        sector = sentiment.get("sector", "")

        # impact_score: score를 그대로 사용 (-1.0 ~ +1.0)
        impact_score_val = Decimal(str(round(score, 3))) if score else None

        mappings.append({
            "article_id": article_ids[idx],
            "score": Decimal(str(round(score, 3))),
            "label": label,
            "news_category": news_category or None,
            "impact_summary": impact_text or None,
            "sector": sector or None,
            "impact_score": impact_score_val,
            "sentiment_item": sentiment,
        })

    if not mappings:
        return 0

    matcher = None
    if stock_name_map:
        from app.utils.stock_matcher import StockMatcher
        matcher = StockMatcher(stock_name_map)

    for mapping in mappings:
        stmt = (
            update(NewsArticle)
            .where(NewsArticle.id == mapping["article_id"])
            .values(
                sentiment_score=mapping["score"],
                sentiment_label=mapping["label"],
                news_category=mapping["news_category"],
                impact_summary=mapping["impact_summary"],
                sector=mapping["sector"],
                impact_score=mapping["impact_score"],
            )
        )
        result = await session.execute(stmt)
        updated += result.rowcount

        # NewsStockImpact 생성
        if matcher:
            s_item = mapping["sentiment_item"]
            llm_names = s_item.get("names", [])
            impact_text = s_item.get("impact", "")
            sentiment_label = s_item.get("sentiment", "neutral")
            score_val = s_item.get("score")

            for lname in llm_names:
                matched = matcher.match(lname)
                if matched:
                    direction = (
                        "bullish" if sentiment_label == "positive"
                        else ("bearish" if sentiment_label == "negative" else "neutral")
                    )
                    from app.service.db_service import save_news_impact
                    await save_news_impact(
                        session,
                        news_article_id=mapping["article_id"],
                        stock_id=matched[0],
                        impact_direction=direction,
                        impact_score=score_val,
                        reason=impact_text,
                    )

    await session.flush()

    logger.info("news_sentiment_updated", updated_count=updated, total=len(mappings))

    return updated
