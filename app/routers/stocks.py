"""주식 API 라우터."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.claude_runner import ClaudeRunner
from app.analysis.prompts import build_analysis_prompt
from app.core.auth import check_rate_limit, verify_api_key
from app.core.config import settings
from app.database.session import async_session_factory, get_db
from app.analysis.accuracy import get_accuracy_stats
from app.service.db_service import (
    get_daily_prices,
    get_latest_analysis,
    get_recent_news,
    get_stock_by_ticker,
    list_stocks as db_list_stocks,
    save_analysis_report,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["stocks"], dependencies=[Depends(verify_api_key)])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _decimal_to_float(v: Decimal | None) -> float | None:
    """Decimal을 JSON 직렬화 가능한 float으로 변환한다."""
    if v is None:
        return None
    return float(v)


@router.get("/accuracy")
async def get_accuracy(
    session: DbSession,
    days: int = Query(default=90, ge=7, le=365, description="조회 기간 (일)"),
) -> dict[str, Any]:
    """추천 적중률 통계를 반환한다."""
    stats = await get_accuracy_stats(session, days)

    def _convert(v: Any) -> Any:
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, dict):
            return {k: _convert(val) for k, val in v.items()}
        return v

    return {k: _convert(v) for k, v in stats.items()}


@router.get("/stocks")
async def list_stocks(
    session: DbSession,
    market: str | None = Query(default=None, description="시장 필터 (KRX, NYSE 등)"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """종목 목록을 반환한다."""
    stocks, total = await db_list_stocks(session, market=market, limit=limit, offset=offset)
    return {
        "stocks": [
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
                "sector": s.sector,
            }
            for s in stocks
        ],
        "total": total,
    }


@router.get("/stocks/{ticker}/prices")
async def get_stock_prices(
    ticker: str,
    session: DbSession,
    start_date: date | None = Query(default=None, description="조회 시작일"),
    end_date: date | None = Query(default=None, description="조회 종료일"),
    limit: int = Query(default=60, ge=1, le=365),
) -> dict[str, Any]:
    """종목 가격 히스토리를 반환한다."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    prices = await get_daily_prices(
        session, stock.id, start_date=start_date, end_date=end_date, limit=limit,
    )
    return {
        "ticker": ticker,
        "prices": [
            {
                "trade_date": str(p.trade_date),
                "open": _decimal_to_float(p.open),
                "high": _decimal_to_float(p.high),
                "low": _decimal_to_float(p.low),
                "close": _decimal_to_float(p.close),
                "volume": p.volume,
            }
            for p in prices
        ],
    }


@router.get("/stocks/{ticker}/analysis")
async def get_stock_analysis(ticker: str, session: DbSession) -> dict[str, Any]:
    """최근 분석 리포트를 반환한다."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    report = await get_latest_analysis(session, stock.id)
    if not report:
        return {"ticker": ticker, "analysis": None}

    return {
        "ticker": ticker,
        "analysis": {
            "analysis_date": str(report.analysis_date),
            "analysis_type": report.analysis_type,
            "summary": report.summary,
            "recommendation": report.recommendation,
            "confidence": _decimal_to_float(report.confidence),
            "target_price": _decimal_to_float(report.target_price),
            "key_factors": report.key_factors,
            "bull_case": report.bull_case,
            "bear_case": report.bear_case,
            "model_used": report.model_used,
            "created_at": str(report.created_at) if report.created_at else None,
        },
    }


@router.get("/market/overview")
async def get_market_overview() -> dict[str, Any]:
    """시장 개요를 반환한다."""
    # TODO: 주요 지수(KOSPI, KOSDAQ, S&P500, NASDAQ) 및 환율 데이터 조회
    return {
        "indices": [],
        "exchange_rates": [],
        "updated_at": None,
    }


async def _run_analysis(ticker: str) -> None:
    """백그라운드에서 Claude 분석을 실행한다."""
    logger.info("on_demand_analysis_started", ticker=ticker)

    async with async_session_factory() as session:
        try:
            stock = await get_stock_by_ticker(session, ticker)
            if not stock:
                logger.error("on_demand_analysis_stock_not_found", ticker=ticker)
                return

            prices = await get_daily_prices(session, stock.id, limit=5)
            news = await get_recent_news(session, stock_id=stock.id, limit=5)

            prices_summary = "\n".join(
                f"{p.trade_date}: 종가 {float(p.close):,.0f} / 거래량 {p.volume:,}"
                for p in prices
            ) or "가격 데이터 없음"

            news_summary = "\n".join(
                f"- {n.title}" for n in news
            ) or "관련 뉴스 없음"

            prompt = build_analysis_prompt(
                ticker=stock.ticker,
                name=stock.name,
                prices_summary=prices_summary,
                news_summary=news_summary,
                market_context=f"시장: {stock.market}",
            )

            runner = ClaudeRunner(
                claude_path=settings.CLAUDE_PATH,
                timeout=settings.CLAUDE_TIMEOUT,
            )
            result = await runner.run(prompt)

            if not isinstance(result, dict):
                logger.error("on_demand_analysis_invalid_result", ticker=ticker)
                return

            await save_analysis_report(
                session,
                stock_id=stock.id,
                analysis_date=date.today(),
                analysis_type="on_demand",
                result=result,
                model_used="claude-code-headless",
            )
            await session.commit()
            logger.info("on_demand_analysis_completed", ticker=ticker)
        except Exception as e:
            await session.rollback()
            logger.exception("on_demand_analysis_failed", ticker=ticker, error=str(e))


@router.post(
    "/stocks/{ticker}/analysis/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(check_rate_limit)],
)
async def request_stock_analysis(
    ticker: str,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """온디맨드 Claude 분석을 트리거한다."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    background_tasks.add_task(_run_analysis, ticker)
    logger.info("on_demand_analysis_queued", ticker=ticker)
    return {
        "ticker": ticker,
        "status": "accepted",
        "message": f"{ticker} 분석이 대기열에 추가되었습니다.",
    }
