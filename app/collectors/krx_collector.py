"""한국 주식 데이터 수집기 (pykrx + FinanceDataReader)."""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd
import structlog
from pykrx import stock as pykrx_stock

from app.utils.market_calendar import is_krx_trading_day

logger = structlog.get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _collect_krx_ohlcv_sync(target_date: date) -> pd.DataFrame:
    """KRX 전종목 OHLCV를 동기로 수집한다."""
    if not is_krx_trading_day(target_date):
        logger.info("krx_ohlcv_skip_non_trading_day", date=str(target_date))
        return pd.DataFrame()

    date_str = target_date.strftime("%Y%m%d")
    logger.info("krx_ohlcv_collecting", date=date_str)
    df = pykrx_stock.get_market_ohlcv_by_ticker(date_str, market="ALL")
    logger.info("krx_ohlcv_collected", date=date_str, rows=len(df))
    return df


async def collect_krx_ohlcv(target_date: date | None = None) -> pd.DataFrame:
    """KRX 전종목 OHLCV를 수집한다.

    Args:
        target_date: 수집 대상 날짜. None이면 오늘(KST 기준).

    Returns:
        OHLCV DataFrame. 비거래일이면 빈 DataFrame.
    """
    if target_date is None:
        target_date = datetime.now(tz=KST).date()
    return await asyncio.to_thread(_collect_krx_ohlcv_sync, target_date)


def _collect_stock_listing_sync() -> pd.DataFrame:
    """KRX 상장 종목 목록을 동기로 수집한다."""
    logger.info("krx_stock_listing_collecting")
    df = fdr.StockListing("KRX")
    logger.info("krx_stock_listing_collected", rows=len(df))
    return df


async def collect_stock_listing() -> pd.DataFrame:
    """KRX 상장 종목 목록을 수집한다.

    Returns:
        종목 코드, 이름, 시장 등 정보가 담긴 DataFrame.
    """
    return await asyncio.to_thread(_collect_stock_listing_sync)


def _collect_investor_trading_sync(
    ticker: str, start: str, end: str
) -> pd.DataFrame:
    """외국인/기관 순매수 데이터를 동기로 수집한다."""
    logger.info(
        "krx_investor_trading_collecting",
        ticker=ticker,
        start=start,
        end=end,
    )
    df = pykrx_stock.get_market_trading_value_by_date(start, end, ticker)
    logger.info(
        "krx_investor_trading_collected",
        ticker=ticker,
        rows=len(df),
    )
    return df


async def collect_investor_trading(
    ticker: str, start: str, end: str
) -> pd.DataFrame:
    """외국인/기관 순매수 데이터를 수집한다.

    Args:
        ticker: 종목 코드 (예: "005930").
        start: 조회 시작일 (예: "20260101").
        end: 조회 종료일 (예: "20260416").

    Returns:
        투자자별 순매수 금액 DataFrame.
    """
    return await asyncio.to_thread(
        _collect_investor_trading_sync, ticker, start, end
    )
