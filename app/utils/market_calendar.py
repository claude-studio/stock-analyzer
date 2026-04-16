"""KRX/NYSE 거래일 판단 유틸리티 (pandas_market_calendars 기반)."""

import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import structlog

logger = structlog.get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

KRX_OPEN = time(9, 0)
KRX_CLOSE = time(15, 30)


def _is_trading_day(exchange: str, dt: date) -> bool:
    """지정 거래소의 거래일 여부를 판단한다."""
    cal = mcal.get_calendar(exchange)
    start = datetime(dt.year, dt.month, dt.day)
    end = start
    schedule = cal.schedule(start_date=start, end_date=end)
    return len(schedule) > 0


def is_krx_trading_day(dt: date | None = None) -> bool:
    """KRX 거래일 여부를 반환한다.

    Args:
        dt: 판단 대상 날짜. None이면 오늘(KST 기준).
    """
    if dt is None:
        dt = datetime.now(tz=KST).date()
    result = _is_trading_day("XKRX", dt)
    logger.debug("krx_trading_day_check", date=str(dt), is_trading_day=result)
    return result


def is_nyse_trading_day(dt: date | None = None) -> bool:
    """NYSE 거래일 여부를 반환한다.

    Args:
        dt: 판단 대상 날짜. None이면 오늘(ET 기준).
    """
    if dt is None:
        dt = datetime.now(tz=ET).date()
    result = _is_trading_day("XNYS", dt)
    logger.debug("nyse_trading_day_check", date=str(dt), is_trading_day=result)
    return result


def is_krx_market_open() -> bool:
    """현재 KRX 장중(09:00-15:30 KST)인지 판단한다.

    거래일이 아니면 False를 반환한다.
    """
    now_kst = datetime.now(tz=KST)
    if not is_krx_trading_day(now_kst.date()):
        return False
    current_time = now_kst.time()
    is_open = KRX_OPEN <= current_time <= KRX_CLOSE
    logger.debug(
        "krx_market_open_check",
        current_time=str(current_time),
        is_open=is_open,
    )
    return is_open


async def async_is_krx_trading_day(dt: date | None = None) -> bool:
    """is_krx_trading_day의 async 래퍼."""
    return await asyncio.to_thread(is_krx_trading_day, dt)


async def async_is_nyse_trading_day(dt: date | None = None) -> bool:
    """is_nyse_trading_day의 async 래퍼."""
    return await asyncio.to_thread(is_nyse_trading_day, dt)
