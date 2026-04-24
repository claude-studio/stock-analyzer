"""주간 Reflection 루프 모듈.

매주 금요일 적중률을 분석하고 편향 패턴을 식별하여 개선점을 도출한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.accuracy import get_accuracy_stats
from app.analysis.claude_runner import ClaudeRunner
from app.database.models import NewsArticle, NewsStockImpact, Stock, StockRelation
from app.utils.discord import send_alert

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")

REFLECTION_LOG_PATH = Path(__file__).parent / "reflection_log.json"

_REFLECTION_PROMPT_TEMPLATE = """\
당신은 투자 분석 시스템의 메타 분석가입니다.
아래는 최근 90일간의 추천 적중률 통계입니다.

## 전체 통계
- 총 평가 건수: {total}
- 7일 적중률: {hit_rate_7d:.1%} (적중 {hit_7d} / 미적중 {miss_7d})
- 30일 적중률: {hit_rate_30d:.1%} (적중 {hit_30d} / 미적중 {miss_30d})

## 추천 유형별 적중률
{by_recommendation_text}

## 분석 요청
1. 적중률 40% 이하인 추천 유형에 대해 편향 패턴을 분석하세요.
2. 과매수/과매도 신호 무시, 뉴스 과잉 반응 등 체계적 편향이 있는지 식별하세요.
3. 개선을 위한 구체적 제안을 3가지 이내로 제시하세요.

JSON 형식으로 응답하세요:
{{
  "bias_analysis": "편향 분석 결과",
  "weak_areas": ["취약 영역 1", "취약 영역 2"],
  "improvements": ["개선 제안 1", "개선 제안 2", "개선 제안 3"]
}}
"""


async def run_weekly_reflection(
    runner: ClaudeRunner,
    session: AsyncSession,
) -> str:
    """주간 Reflection을 실행한다.

    1. get_accuracy_stats(session, days=90)로 적중률 통계
    2. recommendation별 적중률 분석
    3. 적중률 40% 이하 유형에 대해 Claude에 편향 분석 요청
    4. 결과를 reflection_log.json에 append
    5. Discord에 reflection 결과 요약 전송

    Returns:
        reflection 결과 요약 텍스트
    """
    stats = await get_accuracy_stats(session, days=90)

    # 추천 유형별 텍스트 생성
    by_rec = stats.get("by_recommendation", {})
    rec_lines: list[str] = []
    low_accuracy_types: list[str] = []

    for rec_type, rec_stats in by_rec.items():
        hit_rate = rec_stats.get("hit_rate_7d", 0.0)
        count = rec_stats.get("count", 0)
        rec_lines.append(f"- {rec_type}: 7일 적중률 {hit_rate:.1%} (건수: {count})")
        if hit_rate < 0.4 and count >= 3:
            low_accuracy_types.append(rec_type)

    by_recommendation_text = "\n".join(rec_lines) if rec_lines else "데이터 없음"

    # 적중률이 전반적으로 낮거나 특정 유형이 취약하면 Claude 분석 요청
    if stats.get("total", 0) < 5:
        summary = "평가 데이터가 부족하여 Reflection을 건너뜁니다."
        logger.info("reflection_skipped", reason="insufficient_data", total=stats.get("total", 0))
        return summary

    prompt = _REFLECTION_PROMPT_TEMPLATE.format(
        total=stats["total"],
        hit_rate_7d=stats["hit_rate_7d"],
        hit_7d=stats["hit_7d"],
        miss_7d=stats["miss_7d"],
        hit_rate_30d=stats["hit_rate_30d"],
        hit_30d=stats["hit_30d"],
        miss_30d=stats["miss_30d"],
        by_recommendation_text=by_recommendation_text,
    )

    try:
        result = await runner.run(prompt, output_format="json")
    except (RuntimeError, TimeoutError) as e:
        logger.warning("reflection_claude_failed", error=str(e))
        return f"Reflection Claude 호출 실패: {e}"

    # 결과 파싱
    reflection_data: dict = {}
    if isinstance(result, dict):
        reflection_data = result
    elif isinstance(result, str):
        try:
            reflection_data = json.loads(result)
        except json.JSONDecodeError:
            reflection_data = {"bias_analysis": result, "weak_areas": [], "improvements": []}

    # reflection_log.json에 append
    log_entry = {
        "timestamp": datetime.now(tz=KST).isoformat(),
        "stats": stats,
        "low_accuracy_types": low_accuracy_types,
        "reflection": reflection_data,
    }
    _append_reflection_log(log_entry)

    # Discord 알림
    summary_lines = [
        f"7일 적중률: {stats['hit_rate_7d']:.1%}",
        f"30일 적중률: {stats['hit_rate_30d']:.1%}",
    ]
    if low_accuracy_types:
        summary_lines.append(f"취약 유형: {', '.join(low_accuracy_types)}")

    bias = reflection_data.get("bias_analysis", "")
    if bias:
        summary_lines.append(f"편향 분석: {bias[:200]}")

    improvements = reflection_data.get("improvements", [])
    if improvements:
        summary_lines.append("개선 제안:")
        for imp in improvements[:3]:
            summary_lines.append(f"  - {imp}")

    summary = "\n".join(summary_lines)

    try:
        await send_alert(
            title="주간 Reflection 결과",
            message=summary,
            color=0x9B59B6,
        )
    except Exception:
        logger.warning("reflection_discord_failed", exc_info=True)

    logger.info(
        "reflection_completed",
        total=stats["total"],
        hit_rate_7d=stats["hit_rate_7d"],
        low_accuracy_types=low_accuracy_types,
    )

    # 관계 갱신
    try:
        await _update_relations_from_news(runner, session)
    except Exception:
        logger.warning("relation_update_failed", exc_info=True)

    return summary


_RELATION_UPDATE_PROMPT = """\
현재 종목 관계 데이터와 최근 1주간 뉴스에서 감지된 시그널을 비교하라.

## 현재 관계
{current_relations}

## 최근 1주 뉴스 시그널
{news_signals}

신규/변경/소멸 관계를 JSON 배열로 응답하라.
변경이 없으면 빈 배열 []을 반환하라.

형식:
[
  {{"action": "add|update|remove", "source_ticker": "005930", "target_ticker": "000660"}}
]
"""


async def _update_relations_from_news(
    runner: ClaudeRunner,
    session: AsyncSession,
) -> None:
    """최근 1주 뉴스에서 감지된 관계 변화를 반영한다."""
    from datetime import timedelta

    cutoff = datetime.now(tz=KST) - timedelta(days=7)

    # 현재 관계 조회
    rel_stmt = (
        select(
            StockRelation.relation_type,
            StockRelation.strength,
            StockRelation.context,
            Stock.ticker,
            Stock.name,
        )
        .join(Stock, StockRelation.target_stock_id == Stock.id)
        .order_by(StockRelation.source_stock_id)
        .limit(200)
    )
    rel_result = await session.execute(rel_stmt)
    rel_rows = rel_result.all()

    if not rel_rows:
        logger.info("relation_update_skipped", reason="no_existing_relations")
        return

    current_lines: list[str] = []
    for rel_type, strength, context, ticker, name in rel_rows:
        s_val = f" ({float(strength):.1f})" if strength else ""
        ctx_val = f" - {context}" if context else ""
        current_lines.append(f"- {name}({ticker}) [{rel_type}]{s_val}{ctx_val}")

    # 최근 7일 뉴스 시그널 (secondary_impacts 패턴이 있는 것)
    news_stmt = (
        select(NewsStockImpact.reason, Stock.name, Stock.ticker)
        .join(Stock, NewsStockImpact.stock_id == Stock.id)
        .join(NewsArticle, NewsStockImpact.news_article_id == NewsArticle.id)
        .where(NewsArticle.published_at >= cutoff)
        .where(NewsStockImpact.reason.isnot(None))
        .order_by(NewsArticle.published_at.desc())
        .limit(50)
    )
    news_result = await session.execute(news_stmt)
    news_rows = news_result.all()

    if not news_rows:
        logger.info("relation_update_skipped", reason="no_recent_news_signals")
        return

    signal_lines: list[str] = []
    for reason, name, ticker in news_rows:
        signal_lines.append(f"- {name}({ticker}): {reason[:200]}")

    prompt = _RELATION_UPDATE_PROMPT.format(
        current_relations="\n".join(current_lines[:100]),
        news_signals="\n".join(signal_lines[:50]),
    )

    try:
        result = await runner.run(prompt, output_format="json")
    except (RuntimeError, TimeoutError) as e:
        logger.warning("relation_update_claude_failed", error=str(e))
        return

    changes: list[dict] = []
    if isinstance(result, list):
        changes = result
    elif isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list):
                changes = parsed
        except json.JSONDecodeError:
            pass

    if not changes:
        logger.info("relation_update_no_changes")
        return

    from app.service.db_service import get_stock_id_map, upsert_stock_relation

    stock_id_map = await get_stock_id_map(session)
    updated_count = 0

    for change in changes:
        action = change.get("action", "")
        source_ticker = change.get("source_ticker", "")
        target_ticker = change.get("target_ticker", "")
        source_id = stock_id_map.get(source_ticker)
        target_id = stock_id_map.get(target_ticker)

        if not source_id or not target_id:
            continue

        if action in ("add", "update"):
            await upsert_stock_relation(
                session,
                source_stock_id=source_id,
                target_stock_id=target_id,
                relation_type=change.get("type", "sector_peer"),
                strength=change.get("strength"),
                context=change.get("context"),
                source="news_cooccurrence",
            )
            updated_count += 1
        elif action == "remove":
            del_stmt = (
                select(StockRelation)
                .where(
                    StockRelation.source_stock_id == source_id,
                    StockRelation.target_stock_id == target_id,
                    StockRelation.relation_type == change.get("type", ""),
                )
            )
            del_result = await session.execute(del_stmt)
            rel_to_delete = del_result.scalar_one_or_none()
            if rel_to_delete:
                await session.delete(rel_to_delete)
                updated_count += 1

    await session.flush()

    if updated_count > 0:
        try:
            await send_alert(
                title="종목 관계 갱신",
                message=f"뉴스 기반 관계 갱신 {updated_count}건 반영",
                color=0x3498DB,
            )
        except Exception:
            logger.warning("relation_update_discord_failed", exc_info=True)

    logger.info("relation_update_completed", updated_count=updated_count)


def _append_reflection_log(entry: dict) -> None:
    """reflection_log.json에 항목을 추가한다."""
    logs: list[dict] = []
    if REFLECTION_LOG_PATH.exists():
        try:
            logs = json.loads(REFLECTION_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logs = []

    logs.append(entry)

    # 최대 52주(1년) 분량만 유지
    if len(logs) > 52:
        logs = logs[-52:]

    REFLECTION_LOG_PATH.write_text(
        json.dumps(logs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
