"""적중률 평가 로직."""

from datetime import date, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AccuracyTracker, AnalysisReport, DailyPrice, Stock

logger = structlog.get_logger(__name__)

_BUY_RECOMMENDATIONS = {"buy", "strong_buy"}
_SELL_RECOMMENDATIONS = {"sell", "strong_sell"}
_HOLD_THRESHOLD = Decimal("0.03")
_TRADE_COST = Decimal("0.005")  # 편도 0.5% 거래비용 가정 (매수 0.015% + 매도 0.25% + 슬리피지 0.1%)
_USER_FACING_ANALYSIS_TYPE = "daily"


def _judge_hit(recommendation: str, actual_return: Decimal | None) -> bool | None:
    """추천 방향과 실제 수익률을 비교하여 적중 여부 판단."""
    if actual_return is None:
        return None
    if recommendation in _BUY_RECOMMENDATIONS:
        return actual_return > _TRADE_COST
    if recommendation in _SELL_RECOMMENDATIONS:
        return actual_return < -_TRADE_COST
    if recommendation == "hold":
        return abs(actual_return) < _HOLD_THRESHOLD
    return None


async def _find_close_price(
    session: AsyncSession,
    stock_id: int,
    target_date: date,
    tolerance_days: int = 3,
) -> Decimal | None:
    """target_date 기준으로 가장 가까운 종가 조회 (거래일 보정)."""
    stmt = (
        select(DailyPrice.close)
        .where(
            DailyPrice.stock_id == stock_id,
            DailyPrice.trade_date >= target_date - timedelta(days=tolerance_days),
            DailyPrice.trade_date <= target_date + timedelta(days=tolerance_days),
        )
        .order_by(
            func.abs(
                func.extract("epoch", DailyPrice.trade_date)
                - func.extract("epoch", target_date)
            )
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def evaluate_past_analyses(session: AsyncSession, lookback_days: int = 7) -> dict:
    """N일 전 분석 결과를 현재 주가와 비교하여 적중률 평가.

    Returns:
        {"evaluated": int, "hit": int, "miss": int, "hit_rate": float}
    """
    target_date = date.today() - timedelta(days=lookback_days)

    # 대상 리포트 조회 (이미 평가된 것 제외)
    existing_ids_subq = select(AccuracyTracker.analysis_report_id).scalar_subquery()
    stmt = (
        select(AnalysisReport)
        .join(Stock, AnalysisReport.stock_id == Stock.id)
        .where(
            AnalysisReport.analysis_date == target_date,
            AnalysisReport.analysis_type == _USER_FACING_ANALYSIS_TYPE,
            AnalysisReport.id.notin_(existing_ids_subq),
        )
    )
    result = await session.execute(stmt)
    reports = result.scalars().all()

    evaluated = 0
    hit_count = 0
    miss_count = 0

    for report in reports:
        stock = await session.get(Stock, report.stock_id)
        if stock is None:
            continue

        entry_price = await _find_close_price(session, report.stock_id, report.analysis_date)
        if entry_price is None:
            logger.warning(
                "entry_price 조회 실패",
                ticker=stock.ticker,
                analysis_date=str(report.analysis_date),
            )
            continue

        price_7d = await _find_close_price(
            session, report.stock_id, report.analysis_date + timedelta(days=7)
        )
        price_30d = await _find_close_price(
            session, report.stock_id, report.analysis_date + timedelta(days=30)
        )

        return_7d = (
            (price_7d - entry_price) / entry_price if price_7d and entry_price else None
        )
        return_30d = (
            (price_30d - entry_price) / entry_price if price_30d and entry_price else None
        )

        recommendation = report.recommendation or "hold"
        hit_7d = _judge_hit(recommendation, return_7d)
        hit_30d = _judge_hit(recommendation, return_30d)

        tracker = AccuracyTracker(
            analysis_report_id=report.id,
            ticker=stock.ticker,
            recommendation=recommendation,
            confidence=report.confidence,
            target_price=report.target_price,
            entry_price=entry_price,
            actual_price_7d=price_7d,
            actual_price_30d=price_30d,
            actual_return_7d=return_7d,
            actual_return_30d=return_30d,
            is_hit_7d=hit_7d,
            is_hit_30d=hit_30d,
            evaluated_at=func.now(),
        )
        session.add(tracker)
        evaluated += 1

        if hit_7d is True:
            hit_count += 1
        elif hit_7d is False:
            miss_count += 1

    if evaluated > 0:
        await session.flush()

    hit_rate = hit_count / evaluated if evaluated else 0.0
    logger.info(
        "적중률 평가 완료",
        target_date=str(target_date),
        evaluated=evaluated,
        hit=hit_count,
        miss=miss_count,
        hit_rate=round(hit_rate, 4),
    )
    return {
        "evaluated": evaluated,
        "hit": hit_count,
        "miss": miss_count,
        "hit_rate": round(hit_rate, 4),
    }


async def get_accuracy_stats(session: AsyncSession, days: int = 90) -> dict:
    """최근 N일간 적중률 통계.

    Returns:
        {
            "total": int,
            "hit_7d": int, "miss_7d": int, "hit_rate_7d": float,
            "hit_30d": int, "miss_30d": int, "hit_rate_30d": float,
            "by_recommendation": {
                "strong_buy": {"count": int, "hit_rate_7d": float, "hit_rate_30d": float},
                ...
            }
        }
    """
    cutoff = date.today() - timedelta(days=days)

    # 전체 통계
    total_stmt = (
        select(
            func.count().label("total"),
            func.count(case((AccuracyTracker.is_hit_7d.is_(True), 1))).label("hit_7d"),
            func.count(case((AccuracyTracker.is_hit_7d.is_(False), 1))).label("miss_7d"),
            func.count(case((AccuracyTracker.is_hit_30d.is_(True), 1))).label("hit_30d"),
            func.count(case((AccuracyTracker.is_hit_30d.is_(False), 1))).label("miss_30d"),
        )
        .join(AnalysisReport, AccuracyTracker.analysis_report_id == AnalysisReport.id)
        .where(AccuracyTracker.created_at >= cutoff)
        .where(AnalysisReport.analysis_type == _USER_FACING_ANALYSIS_TYPE)
        .where(AnalysisReport.analysis_date >= cutoff)
    )
    result = await session.execute(total_stmt)
    row = result.one()

    total = row.total
    hit_7d = row.hit_7d
    miss_7d = row.miss_7d
    hit_30d = row.hit_30d
    miss_30d = row.miss_30d

    evaluated_7d = hit_7d + miss_7d
    evaluated_30d = hit_30d + miss_30d

    # recommendation별 통계
    by_rec_stmt = (
        select(
            AccuracyTracker.recommendation,
            func.count().label("count"),
            func.count(case((AccuracyTracker.is_hit_7d.is_(True), 1))).label("hit_7d"),
            func.count(
                case((AccuracyTracker.is_hit_7d.isnot(None), 1))
            ).label("evaluated_7d"),
            func.count(case((AccuracyTracker.is_hit_30d.is_(True), 1))).label("hit_30d"),
            func.count(
                case((AccuracyTracker.is_hit_30d.isnot(None), 1))
            ).label("evaluated_30d"),
        )
        .join(AnalysisReport, AccuracyTracker.analysis_report_id == AnalysisReport.id)
        .where(AccuracyTracker.created_at >= cutoff)
        .where(AnalysisReport.analysis_type == _USER_FACING_ANALYSIS_TYPE)
        .where(AnalysisReport.analysis_date >= cutoff)
        .group_by(AccuracyTracker.recommendation)
    )
    rec_result = await session.execute(by_rec_stmt)
    rec_rows = rec_result.all()

    by_recommendation = {}
    for rec_row in rec_rows:
        rec_eval_7d = rec_row.evaluated_7d
        rec_eval_30d = rec_row.evaluated_30d
        by_recommendation[rec_row.recommendation] = {
            "count": rec_row.count,
            "hit_rate_7d": round(rec_row.hit_7d / rec_eval_7d, 4) if rec_eval_7d else 0.0,
            "hit_rate_30d": round(rec_row.hit_30d / rec_eval_30d, 4) if rec_eval_30d else 0.0,
        }

    return {
        "total": total,
        "hit_7d": hit_7d,
        "miss_7d": miss_7d,
        "hit_rate_7d": round(hit_7d / evaluated_7d, 4) if evaluated_7d else 0.0,
        "hit_30d": hit_30d,
        "miss_30d": miss_30d,
        "hit_rate_30d": round(hit_30d / evaluated_30d, 4) if evaluated_30d else 0.0,
        "by_recommendation": by_recommendation,
    }
