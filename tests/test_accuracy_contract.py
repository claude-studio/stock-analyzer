from __future__ import annotations

from datetime import date as real_date
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.analysis import accuracy as accuracy_module
from app.analysis.accuracy import evaluate_past_analyses, get_accuracy_stats
from app.database.models import AccuracyTracker, AnalysisReport, Stock


class FixedDate(real_date):
    @classmethod
    def today(cls) -> real_date:
        return cls(2026, 4, 27)


@pytest.fixture
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> real_date:
    monkeypatch.setattr(accuracy_module, "date", FixedDate)
    return FixedDate.today()


async def test_evaluate_past_analyses_only_tracks_final_daily_reports_for_target_date(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
    fixed_today: real_date,
) -> None:
    target_date = fixed_today - timedelta(days=7)
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    daily_report = AnalysisReport(
        stock_id=1,
        analysis_date=target_date,
        analysis_type="daily",
        summary="daily",
        recommendation="buy",
        confidence=Decimal("0.80"),
        target_price=Decimal("72000.00"),
        key_factors={"source": "daily"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    analyst_report = AnalysisReport(
        stock_id=1,
        analysis_date=target_date,
        analysis_type="analyst_value",
        summary="analyst shard",
        recommendation="buy",
        confidence=Decimal("0.70"),
        target_price=Decimal("73000.00"),
        key_factors={"source": "analyst"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    test_db.session.add_all([stock, daily_report, analyst_report])
    await test_db.session.flush()

    async def fake_find_close_price(
        session,
        stock_id: int,
        target_date_param,
        tolerance_days: int = 3,
    ):
        del session, tolerance_days
        if target_date_param == target_date:
            return Decimal("100.00")
        if target_date_param == target_date + timedelta(days=7):
            return Decimal("108.00")
        if target_date_param == target_date + timedelta(days=30):
            return Decimal("115.00")
        raise AssertionError(
            f"unexpected target date: {stock_id} / {target_date_param}"
        )

    monkeypatch.setattr(accuracy_module, "_find_close_price", fake_find_close_price)

    result = await evaluate_past_analyses(test_db.session, lookback_days=7)
    trackers = list((await test_db.session.execute(select(AccuracyTracker))).scalars().all())

    assert result == {"evaluated": 1, "hit": 1, "miss": 0, "hit_rate": 1.0}
    assert {tracker.analysis_report_id for tracker in trackers} == {daily_report.id}
    assert {tracker.recommendation for tracker in trackers} == {"buy"}


async def test_evaluate_past_analyses_returns_zero_for_empty_target_window(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
    fixed_today: real_date,
) -> None:
    del fixed_today

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_find_close_price should not be called when no reports exist")

    monkeypatch.setattr(accuracy_module, "_find_close_price", should_not_run)

    result = await evaluate_past_analyses(test_db.session, lookback_days=30)

    assert result == {"evaluated": 0, "hit": 0, "miss": 0, "hit_rate": 0.0}


async def test_get_accuracy_stats_excludes_non_daily_trackers_and_is_zero_safe(
    test_db,
    fixed_today: real_date,
) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    daily_report = AnalysisReport(
        stock_id=1,
        analysis_date=fixed_today - timedelta(days=3),
        analysis_type="daily",
        summary="daily",
        recommendation="buy",
        confidence=Decimal("0.80"),
        target_price=Decimal("72000.00"),
        key_factors={"source": "daily"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    analyst_report = AnalysisReport(
        stock_id=1,
        analysis_date=fixed_today - timedelta(days=3),
        analysis_type="analyst_sentiment",
        summary="analyst shard",
        recommendation="sell",
        confidence=Decimal("0.60"),
        target_price=Decimal("65000.00"),
        key_factors={"source": "analyst"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    test_db.session.add_all([stock, daily_report, analyst_report])
    await test_db.session.flush()

    daily_tracker = AccuracyTracker(
        analysis_report_id=daily_report.id,
        ticker="005930",
        recommendation="buy",
        confidence=Decimal("0.80"),
        target_price=Decimal("72000.00"),
        entry_price=Decimal("100.00"),
        actual_price_7d=Decimal("108.00"),
        actual_price_30d=Decimal("115.00"),
        actual_return_7d=Decimal("0.0800"),
        actual_return_30d=Decimal("0.1500"),
        is_hit_7d=True,
        is_hit_30d=True,
    )
    analyst_tracker = AccuracyTracker(
        analysis_report_id=analyst_report.id,
        ticker="005930",
        recommendation="sell",
        confidence=Decimal("0.60"),
        target_price=Decimal("65000.00"),
        entry_price=Decimal("100.00"),
        actual_price_7d=Decimal("108.00"),
        actual_price_30d=Decimal("115.00"),
        actual_return_7d=Decimal("0.0800"),
        actual_return_30d=Decimal("0.1500"),
        is_hit_7d=False,
        is_hit_30d=False,
    )
    test_db.session.add_all([daily_tracker, analyst_tracker])
    await test_db.session.flush()

    stats = await get_accuracy_stats(test_db.session, days=90)
    empty_window_stats = await get_accuracy_stats(test_db.session, days=1)

    assert stats == {
        "total": 1,
        "hit_7d": 1,
        "miss_7d": 0,
        "hit_rate_7d": 1.0,
        "hit_30d": 1,
        "miss_30d": 0,
        "hit_rate_30d": 1.0,
        "by_recommendation": {
            "buy": {
                "count": 1,
                "hit_rate_7d": 1.0,
                "hit_rate_30d": 1.0,
            }
        },
    }
    assert empty_window_stats == {
        "total": 0,
        "hit_7d": 0,
        "miss_7d": 0,
        "hit_rate_7d": 0.0,
        "hit_30d": 0,
        "miss_30d": 0,
        "hit_rate_30d": 0.0,
        "by_recommendation": {},
    }
