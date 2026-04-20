"""주식 API 라우터."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.claude_runner import ClaudeRunner
from app.analysis.prompts import build_analysis_prompt
from app.analysis.technical import calculate_technical_indicators
from app.core.auth import check_rate_limit, verify_api_key
from app.core.config import settings
from app.database.session import async_session_factory, get_db
from app.analysis.accuracy import get_accuracy_stats
from app.service.db_service import (
    get_daily_prices,
    get_latest_analysis,
    get_news_detail,
    get_news_impact_summary,
    get_recent_news,
    get_recent_news_with_stock,
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


def _prices_to_indicators(prices: list) -> dict[str, Any] | None:
    """DailyPrice 목록을 기술적 지표 dict로 변환한다."""
    if len(prices) < 2:
        return None
    df = pd.DataFrame(
        [
            {
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
                "volume": p.volume,
            }
            for p in prices
        ]
    )
    return calculate_technical_indicators(df)


@router.get("/news")
async def list_news(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    ticker: str | None = Query(default=None),
) -> dict[str, Any]:
    """전체 뉴스 피드 (최근 뉴스 목록)."""
    stock_id: int | None = None
    if ticker:
        stock = await get_stock_by_ticker(session, ticker)
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"종목을 찾을 수 없습니다: {ticker}",
            )
        stock_id = stock.id

    news = await get_recent_news_with_stock(
        session, stock_id=stock_id, ticker=ticker if not stock_id else None, limit=limit,
    )
    return {"news": news, "total": len(news)}


@router.get("/news/{news_id}")
async def get_news_detail_endpoint(
    news_id: int,
    session: DbSession,
) -> dict[str, Any]:
    """뉴스 상세 조회 (영향 분석 포함)."""
    detail = await get_news_detail(session, news_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"뉴스를 찾을 수 없습니다: {news_id}",
        )
    return detail


@router.get("/stocks/{ticker}/technical")
async def get_technical_indicators(ticker: str, session: DbSession) -> dict[str, Any]:
    """기술적 지표 계산 결과."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    prices = await get_daily_prices(session, stock.id, limit=60)
    indicators = _prices_to_indicators(prices)
    if indicators is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"기술적 지표 계산에 필요한 가격 데이터가 부족합니다: {ticker}",
        )

    return {"ticker": ticker, "indicators": indicators}


@router.get("/watchlist")
async def get_watchlist_summary(session: DbSession) -> dict[str, Any]:
    """관심 종목 요약 (대시보드용)."""
    watchlist_items: list[dict[str, Any]] = []

    for ticker in settings.KR_WATCHLIST:
        stock = await get_stock_by_ticker(session, ticker)
        if not stock:
            continue

        prices = await get_daily_prices(session, stock.id, limit=2)
        report = await get_latest_analysis(session, stock.id)

        close_val: float | None = None
        change_pct: float | None = None
        volume: int | None = None

        if prices:
            latest = prices[-1]
            close_val = float(latest.close)
            volume = latest.volume
            if len(prices) >= 2:
                prev_close = float(prices[-2].close)
                if prev_close > 0:
                    change_pct = round((close_val - prev_close) / prev_close * 100, 2)

        watchlist_items.append({
            "ticker": stock.ticker,
            "name": stock.name,
            "close": close_val,
            "change_pct": change_pct,
            "volume": volume,
            "recommendation": report.recommendation if report else None,
            "analysis_date": str(report.analysis_date) if report else None,
        })

    return {"watchlist": watchlist_items}


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


@router.get("/stocks/{ticker}/news-impact")
async def get_stock_news_impact(
    ticker: str,
    session: DbSession,
    days: int = Query(default=7, ge=1, le=90, description="조회 기간 (일)"),
) -> dict[str, Any]:
    """종목별 뉴스 영향 분석 요약."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    summary = await get_news_impact_summary(session, stock.id, days=days)
    return {"ticker": ticker, "name": stock.name, **summary}


@router.get("/stocks/{ticker}/detail")
async def get_stock_detail(ticker: str, session: DbSession) -> dict[str, Any]:
    """종목 상세 정보 (프론트엔드 종목 페이지용 통합 API)."""
    stock = await get_stock_by_ticker(session, ticker)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {ticker}",
        )

    prices = await get_daily_prices(session, stock.id, limit=120)
    report = await get_latest_analysis(session, stock.id)
    news = await get_recent_news(session, stock_id=stock.id, limit=10)

    analysis_data: dict[str, Any] | None = None
    if report:
        analysis_data = {
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
        }

    technical_data = _prices_to_indicators(prices)

    return {
        "stock": {
            "ticker": stock.ticker,
            "name": stock.name,
            "market": stock.market,
            "sector": stock.sector,
        },
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
        "analysis": analysis_data,
        "news": [
            {
                "title": n.title,
                "source": n.source,
                "published_at": str(n.published_at) if n.published_at else None,
                "sentiment_label": n.sentiment_label,
                "sentiment_score": _decimal_to_float(n.sentiment_score),
                "news_category": n.news_category,
                "impact_summary": n.impact_summary,
            }
            for n in news
        ],
        "technical": technical_data,
    }


@router.get("/market/overview")
async def get_market_overview() -> dict[str, Any]:
    """KOSPI/KOSDAQ 당일 지수를 조회한다."""
    from pykrx import stock as pykrx_stock

    KST = ZoneInfo("Asia/Seoul")
    today_str = datetime.now(tz=KST).date().strftime("%Y%m%d")

    kospi_data: dict[str, Any] = {"close": None, "change_pct": None}
    kosdaq_data: dict[str, Any] = {"close": None, "change_pct": None}

    try:
        kospi_df, kosdaq_df = await asyncio.gather(
            asyncio.to_thread(
                pykrx_stock.get_index_ohlcv_by_date, today_str, today_str, "1001",
            ),
            asyncio.to_thread(
                pykrx_stock.get_index_ohlcv_by_date, today_str, today_str, "2001",
            ),
        )

        if not kospi_df.empty:
            row = kospi_df.iloc[-1]
            kospi_data = {
                "close": float(row["종가"]),
                "change_pct": float(row["등락률"]),
            }

        if not kosdaq_df.empty:
            row = kosdaq_df.iloc[-1]
            kosdaq_data = {
                "close": float(row["종가"]),
                "change_pct": float(row["등락률"]),
            }
    except Exception:
        logger.warning("market_overview_fetch_failed", exc_info=True)

    return {
        "kospi": kospi_data,
        "kosdaq": kosdaq_data,
        "updated_at": datetime.now(tz=KST).isoformat(),
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
