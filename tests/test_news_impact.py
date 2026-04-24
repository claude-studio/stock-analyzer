"""뉴스 영향 관측 반응 계산 테스트."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.analysis.news_impact import (
    calculate_observed_reaction_from_prices,
    resolve_effective_trading_date,
)
from app.database.models import DailyPrice


def _price(trade_date: date, close: str) -> DailyPrice:
    value = Decimal(close)
    return DailyPrice(
        stock_id=1,
        trade_date=trade_date,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=1000,
    )


def test_kr_after_close_news_maps_to_next_session() -> None:
    published_at = datetime(2026, 4, 24, 16, 30, tzinfo=ZoneInfo("Asia/Seoul"))

    effective_date = resolve_effective_trading_date("KRX", published_at)

    assert effective_date == date(2026, 4, 27)


def test_us_weekend_news_maps_to_next_session() -> None:
    published_at = datetime(2026, 4, 25, 10, 0, tzinfo=ZoneInfo("America/New_York"))

    effective_date = resolve_effective_trading_date("NASDAQ", published_at)

    assert effective_date == date(2026, 4, 27)


def test_calculate_observed_reaction_uses_benchmark_return() -> None:
    stock_prices = [
        _price(date(2026, 4, 27), "100"),
        _price(date(2026, 4, 28), "110"),
    ]
    benchmark_prices = [
        _price(date(2026, 4, 27), "200"),
        _price(date(2026, 4, 28), "204"),
    ]

    reaction = calculate_observed_reaction_from_prices(
        stock_prices=stock_prices,
        benchmark_prices=benchmark_prices,
        market="KRX",
        effective_date=date(2026, 4, 27),
        window_days=1,
    )

    assert reaction.data_status == "raw_price_fallback"
    assert reaction.stock_return == Decimal("0.100000")
    assert reaction.benchmark_return == Decimal("0.020000")
    assert reaction.abnormal_return == Decimal("0.080000")
    assert reaction.car == Decimal("0.080000")
