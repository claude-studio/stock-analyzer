"""주식 API 라우터."""

from datetime import date
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Query, status

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["stocks"])


@router.get("/stocks")
async def list_stocks() -> dict[str, Any]:
    """종목 목록을 반환한다."""
    # TODO: DB에서 stock_listings 테이블 조회
    return {
        "stocks": [],
        "total": 0,
    }


@router.get("/stocks/{ticker}/prices")
async def get_stock_prices(
    ticker: str,
    start_date: date | None = Query(default=None, description="조회 시작일"),
    end_date: date | None = Query(default=None, description="조회 종료일"),
) -> dict[str, Any]:
    """종목 가격 히스토리를 반환한다."""
    # TODO: DB에서 stocks_ohlcv 테이블 조회 (ticker, start_date, end_date 필터)
    return {
        "ticker": ticker,
        "start_date": str(start_date) if start_date else None,
        "end_date": str(end_date) if end_date else None,
        "prices": [],
    }


@router.get("/stocks/{ticker}/analysis")
async def get_stock_analysis(ticker: str) -> dict[str, Any]:
    """최근 분석 리포트를 반환한다."""
    # TODO: DB에서 analysis_reports 테이블 조회 (ticker 기준 최신 1건)
    return {
        "ticker": ticker,
        "analysis": None,
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
    # TODO: Claude CLI로 종목 분석 실행 후 analysis_reports에 저장
    logger.info("on_demand_analysis_started", ticker=ticker)


@router.post(
    "/stocks/{ticker}/analysis/request",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_stock_analysis(
    ticker: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """온디맨드 Claude 분석을 트리거한다."""
    background_tasks.add_task(_run_analysis, ticker)
    logger.info("on_demand_analysis_queued", ticker=ticker)
    return {
        "ticker": ticker,
        "status": "accepted",
        "message": f"{ticker} 분석이 대기열에 추가되었습니다.",
    }
