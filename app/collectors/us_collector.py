"""미국 주식 데이터 수집기 (yfinance)."""

import asyncio

import pandas as pd
import structlog
import yfinance as yf

logger = structlog.get_logger(__name__)


def _collect_us_ohlcv_sync(
    tickers: list[str], period: str
) -> pd.DataFrame:
    """미국 주식 OHLCV를 동기로 수집한다."""
    ticker_str = " ".join(tickers)
    logger.info(
        "us_ohlcv_collecting",
        tickers=tickers,
        period=period,
    )
    df = yf.download(tickers=ticker_str, period=period, progress=False)
    logger.info("us_ohlcv_collected", rows=len(df))
    return df


async def collect_us_ohlcv(
    tickers: list[str], period: str = "1d"
) -> pd.DataFrame:
    """미국 주식 OHLCV를 수집한다.

    Args:
        tickers: 종목 심볼 리스트 (예: ["AAPL", "MSFT"]).
        period: 조회 기간 (예: "1d", "5d", "1mo").

    Returns:
        OHLCV DataFrame.
    """
    return await asyncio.to_thread(_collect_us_ohlcv_sync, tickers, period)


def _collect_us_intraday_sync(tickers: list[str]) -> pd.DataFrame:
    """미국 주식 60분봉 스냅샷을 동기로 수집한다."""
    ticker_str = " ".join(tickers)
    logger.info("us_intraday_collecting", tickers=tickers)
    df = yf.download(
        tickers=ticker_str,
        period="1d",
        interval="60m",
        progress=False,
    )
    logger.info("us_intraday_collected", rows=len(df))
    return df


async def collect_us_intraday(tickers: list[str]) -> pd.DataFrame:
    """미국 주식 60분봉 스냅샷을 수집한다.

    Args:
        tickers: 종목 심볼 리스트 (예: ["AAPL", "MSFT"]).

    Returns:
        60분봉 OHLCV DataFrame.
    """
    return await asyncio.to_thread(_collect_us_intraday_sync, tickers)
