"""뉴스 이벤트의 일봉 기준 관측 가격 반응 계산."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import structlog

from app.database.models import DailyPrice

logger = structlog.get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
KR_AFTER_CLOSE = time(hour=15, minute=30)
US_AFTER_CLOSE = time(hour=16, minute=0)
DEFAULT_WINDOWS = (1, 3)


@dataclass(frozen=True)
class ObservedReaction:
    """뉴스 이벤트 이후 일봉 기준 관측 반응."""

    effective_trading_date: date | None
    window_label: str
    benchmark_ticker: str | None
    stock_return: Decimal | None
    benchmark_return: Decimal | None
    abnormal_return: Decimal | None
    car: Decimal | None
    confidence: Decimal | None
    confounded: bool
    data_status: str
    marker_label: str


def normalize_market(market: str | None) -> str:
    """시장 문자열을 KR/US로 정규화한다."""
    value = (market or "").upper()
    if value in {"KR", "KRX", "KOSPI", "KOSDAQ", "KONEX"}:
        return "KR"
    if value in {"US", "NYSE", "NASDAQ", "AMEX"}:
        return "US"
    return "US" if value.startswith(("NAS", "NYS", "AM")) else "KR"


def benchmark_ticker_for_market(market: str | None) -> str:
    """MVP에서 사용할 시장 대표 벤치마크 ticker를 반환한다."""
    value = (market or "").upper()
    if "KOSDAQ" in value:
        return "KOSDAQ"
    if normalize_market(value) == "US":
        return "SPY"
    return "KOSPI"


def resolve_effective_trading_date(market: str | None, published_at: datetime | str) -> date:
    """뉴스 발행 시각을 거래소 기준 영향 관측 거래일로 정규화한다."""
    market_code = normalize_market(market)
    published = _parse_datetime(published_at)
    local_tz = KST if market_code == "KR" else ET
    local_dt = published.astimezone(local_tz)
    candidate = local_dt.date()
    after_close = local_dt.time() >= (KR_AFTER_CLOSE if market_code == "KR" else US_AFTER_CLOSE)
    if after_close:
        candidate += timedelta(days=1)
    return _next_trading_day(market_code, candidate)


def calculate_observed_reaction_from_prices(
    *,
    stock_prices: list[DailyPrice],
    benchmark_prices: list[DailyPrice],
    market: str | None,
    effective_date: date,
    window_days: int = 1,
    confounded: bool = False,
    price_basis: str = "raw_price_fallback",
) -> ObservedReaction:
    """일봉 가격 목록에서 시장 대비 관측 반응을 계산한다."""
    window_label = f"0,+{window_days}D"
    benchmark_ticker = benchmark_ticker_for_market(market)
    stock_return, stock_status = _window_return(stock_prices, effective_date, window_days)
    benchmark_return, benchmark_status = _window_return(
        benchmark_prices,
        effective_date,
        window_days,
    )

    abnormal_return: Decimal | None = None
    car: Decimal | None = None
    data_status = "ok"
    if stock_return is None:
        data_status = stock_status
    elif benchmark_return is None:
        data_status = benchmark_status if benchmark_status != "ok" else "benchmark_missing"
    else:
        abnormal_return = _quantize_return(stock_return - benchmark_return)
        car = abnormal_return
        data_status = price_basis

    confidence = _confidence(
        data_status=data_status,
        confounded=confounded,
        window_days=window_days,
    )
    return ObservedReaction(
        effective_trading_date=effective_date,
        window_label=window_label,
        benchmark_ticker=benchmark_ticker,
        stock_return=stock_return,
        benchmark_return=benchmark_return,
        abnormal_return=abnormal_return,
        car=car,
        confidence=confidence,
        confounded=confounded,
        data_status=data_status,
        marker_label=_marker_label(abnormal_return, data_status, confounded),
    )


def calculate_observed_reaction(
    *,
    ticker: str,
    market: str | None,
    effective_date: str | date,
    windows: list[int] | None = None,
) -> dict[str, object]:
    """QA용 동기 계산 껍데기. 실제 DB 계산은 service 계층에서 수행한다."""
    window_values = windows or list(DEFAULT_WINDOWS)
    parsed_date = (
        date.fromisoformat(effective_date)
        if isinstance(effective_date, str)
        else effective_date
    )
    return {
        "ticker": ticker,
        "market": normalize_market(market),
        "effective_trading_date": parsed_date.isoformat(),
        "windows": [f"0,+{window}D" for window in window_values],
        "data_status": "requires_db_prices",
        "confidence": 0.0,
    }


def _parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed


def _next_trading_day(market_code: str, candidate: date) -> date:
    calendar_name = "XKRX" if market_code == "KR" else "NYSE"
    calendar = mcal.get_calendar(calendar_name)
    start = candidate
    end = candidate + timedelta(days=14)
    schedule = calendar.schedule(start_date=start.isoformat(), end_date=end.isoformat())
    if schedule.empty:
        logger.warning("trading_day_schedule_empty", market=market_code, candidate=str(candidate))
        return _next_weekday(candidate)
    return schedule.index[0].date()


def _next_weekday(candidate: date) -> date:
    current = candidate
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _window_return(
    prices: list[DailyPrice],
    effective_date: date,
    window_days: int,
) -> tuple[Decimal | None, str]:
    ordered = sorted(prices, key=lambda price: price.trade_date)
    start_index = next(
        (idx for idx, price in enumerate(ordered) if price.trade_date >= effective_date),
        None,
    )
    if start_index is None:
        return None, "price_missing"
    end_index = start_index + window_days
    if end_index >= len(ordered):
        return None, "insufficient_window"

    start_close = ordered[start_index].close
    end_close = ordered[end_index].close
    if start_close is None or start_close <= 0 or end_close is None:
        return None, "price_invalid"
    return _quantize_return((end_close - start_close) / start_close), "ok"


def _quantize_return(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def _confidence(*, data_status: str, confounded: bool, window_days: int) -> Decimal:
    if data_status not in {"ok", "raw_price_fallback"}:
        return Decimal("0.000")
    score = Decimal("0.700")
    if confounded:
        score -= Decimal("0.250")
    if window_days > 1:
        score -= Decimal("0.050")
    return max(score, Decimal("0.100")).quantize(Decimal("0.001"))


def _marker_label(abnormal_return: Decimal | None, data_status: str, confounded: bool) -> str:
    if data_status not in {"ok", "raw_price_fallback"} or abnormal_return is None:
        return "관측 불가"
    prefix = "복합 이벤트" if confounded else "뉴스 반응"
    pct = abnormal_return * Decimal("100")
    sign = "+" if pct >= 0 else ""
    return f"{prefix} {sign}{pct:.2f}%"
