"""개인용 백테스트 서비스."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalysisReport
from app.service.db_service import get_daily_prices, get_stock_by_ticker

KST = ZoneInfo("Asia/Seoul")
BUY_RECOMMENDATIONS = {"buy", "strong_buy"}
SELL_RECOMMENDATIONS = {"sell", "strong_sell"}
SUPPORTED_STRATEGY = "daily_recommendation_follow"
BACKTEST_ASSUMPTIONS = [
    "최종 일일 리포트(analysis_type='daily')만 사용합니다.",
    "매수/매도는 해당 일자의 저장된 종가에 체결된 것으로 단순화합니다.",
    "수수료, 세금, 슬리피지, 분할 매매는 반영하지 않습니다.",
]
BACKTEST_LIMITATIONS = [
    "과거 데이터로 단순화한 시뮬레이션이며 실제 체결 품질이나 미래 성과를 보장하지 않습니다.",
    "현재 DB에 저장된 가격과 최종 일일 리포트가 있는 날짜만 평가합니다.",
]


def _as_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_recommendation(recommendation: str | None) -> str | None:
    if not recommendation:
        return None
    return recommendation.strip().lower()


async def run_backtest(
    session: AsyncSession,
    *,
    ticker: str,
    strategy: str,
    start_date: date,
    end_date: date,
    initial_capital: Decimal,
) -> dict:
    """저장된 가격/리포트만으로 단순 백테스트를 실행한다."""
    if strategy != SUPPORTED_STRATEGY:
        raise ValueError(f"지원하지 않는 전략입니다: {strategy}")
    if end_date < start_date:
        raise ValueError("종료일은 시작일보다 빠를 수 없습니다")
    if initial_capital <= 0:
        raise ValueError("초기 자본은 0보다 커야 합니다")

    stock = await get_stock_by_ticker(session, ticker)
    if stock is None:
        raise LookupError(f"종목을 찾을 수 없습니다: {ticker}")

    prices = await get_daily_prices(
        session,
        stock.id,
        start_date=start_date,
        end_date=end_date,
        limit=2000,
    )
    if not prices:
        raise ValueError("백테스트에 필요한 가격 데이터가 없습니다")

    reports_result = await session.execute(
        select(AnalysisReport)
        .where(
            AnalysisReport.stock_id == stock.id,
            AnalysisReport.analysis_type == "daily",
            AnalysisReport.analysis_date >= start_date,
            AnalysisReport.analysis_date <= end_date,
        )
        .order_by(AnalysisReport.analysis_date.asc(), AnalysisReport.created_at.asc())
    )
    reports_by_date = {
        report.analysis_date: report
        for report in reports_result.scalars().all()
    }

    cash_balance = initial_capital
    shares = Decimal("0")
    entry_price: Decimal | None = None
    timeline: list[dict] = []
    wins = 0
    losses = 0
    completed_trades = 0

    for price in prices:
        report = reports_by_date.get(price.trade_date)
        recommendation = _normalize_recommendation(report.recommendation if report else None)
        close_price = Decimal(price.close)

        if recommendation in BUY_RECOMMENDATIONS and shares == 0:
            shares = cash_balance / close_price
            cash_balance = Decimal("0")
            entry_price = close_price
            timeline.append(
                {
                    "trade_date": str(price.trade_date),
                    "event_type": "buy",
                    "price": float(close_price),
                    "recommendation": recommendation,
                    "shares": round(float(shares), 4),
                    "cash_balance": float(cash_balance),
                    "position_value": round(float(shares * close_price), 2),
                    "message": "최종 일일 리포트 매수 의견에 따라 진입했습니다.",
                }
            )
            continue

        if recommendation in SELL_RECOMMENDATIONS and shares > 0 and entry_price is not None:
            cash_balance = shares * close_price
            realized_return = ((close_price - entry_price) / entry_price) * Decimal("100")
            completed_trades += 1
            if realized_return > 0:
                wins += 1
            elif realized_return < 0:
                losses += 1
            timeline.append(
                {
                    "trade_date": str(price.trade_date),
                    "event_type": "sell",
                    "price": float(close_price),
                    "recommendation": recommendation,
                    "shares": round(float(shares), 4),
                    "cash_balance": round(float(cash_balance), 2),
                    "position_value": 0.0,
                    "realized_return_percent": round(float(realized_return), 2),
                    "message": "최종 일일 리포트 매도 의견에 따라 청산했습니다.",
                }
            )
            shares = Decimal("0")
            entry_price = None

    if shares > 0 and entry_price is not None:
        last_price = Decimal(prices[-1].close)
        cash_balance = shares * last_price
        realized_return = ((last_price - entry_price) / entry_price) * Decimal("100")
        completed_trades += 1
        if realized_return > 0:
            wins += 1
        elif realized_return < 0:
            losses += 1
        timeline.append(
            {
                "trade_date": str(prices[-1].trade_date),
                "event_type": "range_end_close",
                "price": float(last_price),
                "recommendation": None,
                "shares": round(float(shares), 4),
                "cash_balance": round(float(cash_balance), 2),
                "position_value": 0.0,
                "realized_return_percent": round(float(realized_return), 2),
                "message": "기간 종료 시점 종가로 열린 포지션을 정리했습니다.",
            }
        )
        shares = Decimal("0")
        entry_price = None

    ending_capital = cash_balance if shares == 0 else shares * Decimal(prices[-1].close)
    total_return = ((ending_capital - initial_capital) / initial_capital) * Decimal("100")

    return {
        "ticker": stock.ticker,
        "name": stock.name,
        "strategy": strategy,
        "generated_at": date.today().isoformat(),
        "assumptions": BACKTEST_ASSUMPTIONS,
        "limitations": BACKTEST_LIMITATIONS,
        "summary": {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "initial_capital": round(float(initial_capital), 2),
            "ending_capital": round(float(ending_capital), 2),
            "total_return_percent": round(float(total_return), 2),
            "completed_trades": completed_trades,
            "wins": wins,
            "losses": losses,
            "open_position": shares > 0,
            "event_count": len(timeline),
        },
        "timeline": timeline,
    }
