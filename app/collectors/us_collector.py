"""미국 주식 데이터 수집기 (yfinance)."""

import asyncio

import pandas as pd
import structlog
import yfinance as yf

logger = structlog.get_logger(__name__)


def _collect_us_ohlcv_sync(
    tickers: list[str], period: str
) -> pd.DataFrame:
    """미국 주식 OHLCV를 티커별 개별 다운로드로 수집한다."""
    logger.info(
        "us_ohlcv_collecting",
        tickers=tickers,
        period=period,
    )
    frames: list[dict] = []
    for ticker in tickers:
        try:
            df = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                continue
            row = df.iloc[-1].to_dict()
            row["_ticker"] = ticker
            row["_date"] = df.index[-1].date()
            frames.append(row)
        except Exception:
            logger.warning("us_ohlcv_fetch_failed", ticker=ticker)

    if not frames:
        return pd.DataFrame()

    result = pd.DataFrame(frames)
    result.index = result["_ticker"]
    result["date"] = result["_date"]
    result = result.drop(columns=["_ticker", "_date"])
    logger.info("us_ohlcv_collected", count=len(result))
    return result


async def collect_us_ohlcv(
    tickers: list[str], period: str = "1d"
) -> pd.DataFrame:
    """미국 주식 OHLCV를 수집한다.

    Args:
        tickers: 종목 심볼 리스트 (예: ["AAPL", "MSFT"]).
        period: 조회 기간 (예: "1d", "5d", "1mo").

    Returns:
        OHLCV DataFrame (index=ticker, 컬럼: Open, High, Low, Close, Volume, date).
    """
    return await asyncio.to_thread(_collect_us_ohlcv_sync, tickers, period)


def _collect_us_intraday_sync(tickers: list[str]) -> pd.DataFrame:
    """미국 주식 60분봉 스냅샷을 티커별 개별 다운로드로 수집한다."""
    logger.info("us_intraday_collecting", tickers=tickers)
    frames: list[dict] = []
    for ticker in tickers:
        try:
            df = yf.download(
                tickers=ticker,
                period="1d",
                interval="60m",
                progress=False,
            )
            if df.empty:
                continue
            row = df.iloc[-1].to_dict()
            row["_ticker"] = ticker
            row["_date"] = df.index[-1].date()
            frames.append(row)
        except Exception:
            logger.warning("us_intraday_fetch_failed", ticker=ticker)

    if not frames:
        return pd.DataFrame()

    result = pd.DataFrame(frames)
    result.index = result["_ticker"]
    result["date"] = result["_date"]
    result = result.drop(columns=["_ticker", "_date"])
    logger.info("us_intraday_collected", count=len(result))
    return result


async def collect_us_intraday(tickers: list[str]) -> pd.DataFrame:
    """미국 주식 60분봉 스냅샷을 수집한다.

    Args:
        tickers: 종목 심볼 리스트 (예: ["AAPL", "MSFT"]).

    Returns:
        60분봉 OHLCV DataFrame (index=ticker, 컬럼: Open, High, Low, Close, Volume, date).
    """
    return await asyncio.to_thread(_collect_us_intraday_sync, tickers)
