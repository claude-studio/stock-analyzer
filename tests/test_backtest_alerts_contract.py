from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.database.models import AnalysisReport, DailyPrice, NewsArticle, Stock

KST = ZoneInfo("Asia/Seoul")


def _load_module(module_name: str):
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"{module_name} 모듈이 필요합니다"
    return importlib.import_module(module_name)


def _build_price(
    *,
    stock_id: int,
    trade_date: date,
    close: str,
    volume: int,
    open: str | None = None,
) -> DailyPrice:
    open_value = open or close
    return DailyPrice(
        stock_id=stock_id,
        trade_date=trade_date,
        open=Decimal(open_value),
        high=Decimal(close),
        low=Decimal(open_value),
        close=Decimal(close),
        volume=volume,
        market_cap=None,
        foreign_ratio=None,
        inst_net_buy=None,
        foreign_net_buy=None,
    )


def _build_report(
    *,
    stock_id: int,
    analysis_date: date,
    analysis_type: str,
    recommendation: str,
    summary: str,
    created_hour: int,
) -> AnalysisReport:
    return AnalysisReport(
        stock_id=stock_id,
        analysis_date=analysis_date,
        analysis_type=analysis_type,
        summary=summary,
        recommendation=recommendation,
        confidence=Decimal("0.70"),
        target_price=Decimal("150.00"),
        key_factors={"source": analysis_type},
        bull_case="bull",
        bear_case="bear",
        model_used="claude-daily",
        created_at=datetime(
            analysis_date.year,
            analysis_date.month,
            analysis_date.day,
            created_hour,
            0,
            tzinfo=KST,
        ),
    )


def _build_news(
    *,
    news_id: int,
    stock_id: int,
    title: str,
    published_at: datetime,
    sentiment_score: str,
) -> NewsArticle:
    score = Decimal(sentiment_score)
    return NewsArticle(
        id=news_id,
        stock_id=stock_id,
        title=title,
        source="연합뉴스",
        url=f"https://example.com/news/{news_id}",
        published_at=published_at,
        sentiment_score=score,
        sentiment_label="positive" if score >= 0 else "negative",
        news_category="market",
        impact_summary=title,
        sector="반도체",
        impact_score=score,
    )


@pytest.mark.asyncio
async def test_run_backtest_returns_deterministic_daily_recommendation_follow_summary(
    test_db,
) -> None:
    backtest_service = _load_module("app.service.backtest_service")

    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="반도체")
    test_db.session.add(stock)
    test_db.session.add_all(
        [
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 21),
                close="100.00",
                volume=1000,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 22),
                close="110.00",
                volume=1200,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 23),
                close="120.00",
                volume=1500,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 24),
                close="115.00",
                volume=900,
            ),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 21),
                analysis_type="daily",
                recommendation="buy",
                summary="final daily buy",
                created_hour=16,
            ),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 23),
                analysis_type="daily",
                recommendation="sell",
                summary="final daily sell",
                created_hour=16,
            ),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 24),
                analysis_type="on_demand",
                recommendation="buy",
                summary="intraday refresh should stay hidden",
                created_hour=9,
            ),
        ]
    )
    await test_db.session.flush()

    payload = await backtest_service.run_backtest(
        test_db.session,
        ticker="005930",
        strategy="daily_recommendation_follow",
        start_date=date(2026, 4, 21),
        end_date=date(2026, 4, 24),
        initial_capital=Decimal("100000.00"),
    )

    assert payload["ticker"] == "005930"
    assert payload["strategy"] == "daily_recommendation_follow"
    assert payload["assumptions"] == [
        "최종 일일 리포트(analysis_type='daily')만 사용합니다.",
        "매수/매도는 해당 일자의 저장된 종가에 체결된 것으로 단순화합니다.",
        "수수료, 세금, 슬리피지, 분할 매매는 반영하지 않습니다.",
    ]
    assert "과거 데이터로 단순화한 시뮬레이션" in payload["limitations"][0]
    assert payload["summary"] == {
        "start_date": "2026-04-21",
        "end_date": "2026-04-24",
        "initial_capital": 100000.0,
        "ending_capital": 120000.0,
        "total_return_percent": 20.0,
        "completed_trades": 1,
        "wins": 1,
        "losses": 0,
        "open_position": False,
        "event_count": 2,
    }
    assert payload["timeline"] == [
        {
            "trade_date": "2026-04-21",
            "event_type": "buy",
            "price": 100.0,
            "recommendation": "buy",
            "shares": 1000.0,
            "cash_balance": 0.0,
            "position_value": 100000.0,
            "message": "최종 일일 리포트 매수 의견에 따라 진입했습니다.",
        },
        {
            "trade_date": "2026-04-23",
            "event_type": "sell",
            "price": 120.0,
            "recommendation": "sell",
            "shares": 1000.0,
            "cash_balance": 120000.0,
            "position_value": 0.0,
            "realized_return_percent": 20.0,
            "message": "최종 일일 리포트 매도 의견에 따라 청산했습니다.",
        },
    ]


@pytest.mark.asyncio
async def test_alert_rule_crud_and_evaluation_trigger_expected_rules_without_duplicate_spam(
    test_db,
) -> None:
    alerts_service = _load_module("app.service.alerts_service")

    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="반도체")
    test_db.session.add(stock)
    test_db.session.add_all(
        [
            _build_price(stock_id=1, trade_date=date(2026, 4, 10), close="90.00", volume=900),
            _build_price(stock_id=1, trade_date=date(2026, 4, 11), close="91.00", volume=920),
            _build_price(stock_id=1, trade_date=date(2026, 4, 12), close="92.00", volume=930),
            _build_price(stock_id=1, trade_date=date(2026, 4, 13), close="93.00", volume=950),
            _build_price(stock_id=1, trade_date=date(2026, 4, 14), close="94.00", volume=970),
            _build_price(stock_id=1, trade_date=date(2026, 4, 15), close="95.00", volume=980),
            _build_price(stock_id=1, trade_date=date(2026, 4, 16), close="96.00", volume=990),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 17),
                close="97.00",
                volume=1000,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 18),
                close="98.00",
                volume=1020,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 19),
                close="99.00",
                volume=1040,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 20),
                close="100.00",
                volume=1050,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 21),
                close="102.00",
                volume=1080,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 22),
                close="105.00",
                volume=1100,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 23),
                close="110.00",
                volume=1200,
            ),
            _build_price(
                stock_id=1,
                trade_date=date(2026, 4, 24),
                close="120.00",
                volume=1500,
            ),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 23),
                analysis_type="daily",
                recommendation="hold",
                summary="previous daily hold",
                created_hour=16,
            ),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 24),
                analysis_type="daily",
                recommendation="buy",
                summary="latest daily buy",
                created_hour=16,
            ),
            _build_news(
                news_id=1,
                stock_id=1,
                title="전주 부정 기사",
                published_at=datetime(2026, 4, 16, 9, 0, tzinfo=KST),
                sentiment_score="-0.30",
            ),
            _build_news(
                news_id=2,
                stock_id=1,
                title="전주 중립 기사",
                published_at=datetime(2026, 4, 17, 9, 0, tzinfo=KST),
                sentiment_score="-0.10",
            ),
            _build_news(
                news_id=3,
                stock_id=1,
                title="최근 호재 기사",
                published_at=datetime(2026, 4, 23, 9, 0, tzinfo=KST),
                sentiment_score="0.30",
            ),
            _build_news(
                news_id=4,
                stock_id=1,
                title="최근 추가 호재 기사",
                published_at=datetime(2026, 4, 24, 9, 0, tzinfo=KST),
                sentiment_score="0.50",
            ),
        ]
    )
    await test_db.session.flush()

    price_rule = await alerts_service.create_alert_rule(
        test_db.session,
        stock=stock,
        rule_type="target_price",
        direction="above",
        threshold_value=Decimal("118.00"),
        name="목표가 돌파",
    )
    rsi_rule = await alerts_service.create_alert_rule(
        test_db.session,
        stock=stock,
        rule_type="rsi_threshold",
        direction="above",
        threshold_value=Decimal("70.00"),
        name="RSI 과열",
    )
    sentiment_rule = await alerts_service.create_alert_rule(
        test_db.session,
        stock=stock,
        rule_type="sentiment_change",
        direction="up",
        threshold_value=Decimal("0.40"),
        name="감성 급변",
        lookback_days=2,
    )
    recommendation_rule = await alerts_service.create_alert_rule(
        test_db.session,
        stock=stock,
        rule_type="recommendation_change",
        target_recommendation="buy",
        name="매수 전환",
    )
    pending_rule = await alerts_service.create_alert_rule(
        test_db.session,
        stock=stock,
        rule_type="target_price",
        direction="above",
        threshold_value=Decimal("130.00"),
        name="아직 대기",
    )
    await test_db.session.flush()

    listed = await alerts_service.list_alert_rules(test_db.session)
    assert [rule["name"] for rule in listed] == [
        "목표가 돌파",
        "RSI 과열",
        "감성 급변",
        "매수 전환",
        "아직 대기",
    ]

    updated_pending_rule = await alerts_service.update_alert_rule(
        test_db.session,
        rule_id=pending_rule["id"],
        threshold_value=Decimal("125.00"),
        name="아직 대기(수정)",
    )
    assert updated_pending_rule["name"] == "아직 대기(수정)"
    assert updated_pending_rule["threshold_value"] == 125.0

    first_result = await alerts_service.evaluate_alert_rules(test_db.session)
    assert first_result["evaluated_count"] == 5
    assert first_result["triggered_count"] == 4
    assert {event["rule_id"] for event in first_result["triggered_events"]} == {
        price_rule["id"],
        rsi_rule["id"],
        sentiment_rule["id"],
        recommendation_rule["id"],
    }
    assert first_result["pending_rules"] == [
        {
            "rule_id": pending_rule["id"],
            "ticker": "005930",
            "rule_type": "target_price",
            "status": "pending",
            "observed_value": 120.0,
            "observed_text": None,
            "baseline_value": None,
            "baseline_text": None,
            "threshold_value": 125.0,
            "threshold_text": None,
            "observed_at": "2026-04-24",
            "message": "최신 종가가 아직 목표가에 도달하지 않았습니다.",
        }
    ]

    events = await alerts_service.list_alert_events(test_db.session)
    assert len(events) == 4
    assert events[0]["status"] == "triggered"
    assert any(event["rule_type"] == "recommendation_change" for event in events)

    second_result = await alerts_service.evaluate_alert_rules(test_db.session)
    assert second_result["evaluated_count"] == 5
    assert second_result["triggered_count"] == 0
    assert second_result["triggered_events"] == []
    assert len(await alerts_service.list_alert_events(test_db.session)) == 4

    deleted = await alerts_service.delete_alert_rule(
        test_db.session,
        rule_id=updated_pending_rule["id"],
    )
    assert deleted == {"deleted": True, "rule_id": updated_pending_rule["id"]}
    remaining_rules = await alerts_service.list_alert_rules(test_db.session)
    assert len(remaining_rules) == 4


def test_stocks_router_registers_backtest_and_alert_routes(stocks_router_module) -> None:
    paths = {route.path for route in stocks_router_module.router.routes}

    assert "/api/v1/backtests/run" in paths
    assert "/api/v1/alerts/rules" in paths
    assert "/api/v1/alerts/rules/{rule_id}" in paths
    assert "/api/v1/alerts/events" in paths
    assert "/api/v1/alerts/evaluate" in paths


@pytest.mark.asyncio
async def test_scheduler_jobs_exposes_personal_alert_evaluation_hook(
    jobs_module,
    monkeypatch,
) -> None:
    captured: list[str] = []

    async def fake_evaluate_alert_rules(session):
        del session
        captured.append("called")
        return {
            "evaluated_count": 2,
            "triggered_count": 1,
            "triggered_events": [],
            "pending_rules": [],
        }

    class FakeSession:
        async def commit(self) -> None:
            captured.append("commit")

        async def rollback(self) -> None:
            captured.append("rollback")

    class FakeSessionFactory:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    monkeypatch.setattr(jobs_module, "async_session_factory", FakeSessionFactory())
    monkeypatch.setattr(
        jobs_module,
        "evaluate_alert_rules",
        fake_evaluate_alert_rules,
        raising=False,
    )

    hook = getattr(jobs_module, "job_evaluate_personal_alerts", None)
    assert hook is not None, "개인용 알림 평가 스케줄러 훅이 필요합니다"

    await hook()

    assert captured == ["called", "commit"]


def test_scheduler_registers_personal_alert_evaluation_job(
    jobs_module,
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "app.scheduler.jobs", jobs_module)
    fake_apscheduler = types.ModuleType("apscheduler")
    fake_apscheduler_schedulers = types.ModuleType("apscheduler.schedulers")
    fake_apscheduler_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")

    class DummyAsyncIOScheduler:
        pass

    fake_apscheduler_asyncio.AsyncIOScheduler = DummyAsyncIOScheduler
    monkeypatch.setitem(sys.modules, "apscheduler", fake_apscheduler)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", fake_apscheduler_schedulers)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.asyncio", fake_apscheduler_asyncio)
    sys.modules.pop("app.scheduler.scheduler", None)

    scheduler_module = importlib.import_module("app.scheduler.scheduler")

    class RecordingScheduler:
        def __init__(self) -> None:
            self.jobs: list[dict] = []

        def add_job(self, func, trigger, **kwargs) -> None:
            self.jobs.append(
                {
                    "func": func,
                    "trigger": trigger,
                    **kwargs,
                }
            )

        def get_jobs(self) -> list[dict]:
            return self.jobs

    scheduler = RecordingScheduler()

    scheduler_module.register_jobs(scheduler)

    personal_alert_job = next(
        job for job in scheduler.jobs if job["id"] == "evaluate_personal_alerts"
    )
    assert personal_alert_job["func"] is jobs_module.job_evaluate_personal_alerts
    assert personal_alert_job["trigger"] == "cron"
    assert personal_alert_job["day_of_week"] == "mon-fri"
    assert personal_alert_job["hour"] == "9-18"
    assert personal_alert_job["minute"] == "0,30"
