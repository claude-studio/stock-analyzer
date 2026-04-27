from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base

if "pandas" not in sys.modules:
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = lambda rows: rows
    fake_pandas.Series = object
    fake_pandas.Timestamp = datetime
    fake_pandas.concat = lambda values, axis=0: values
    fake_pandas.isna = lambda value: value is None
    sys.modules["pandas"] = fake_pandas


if "structlog" not in sys.modules:
    fake_structlog = types.ModuleType("structlog")

    class DummyLogger:
        def info(self, *args, **kwargs) -> None:
            del args, kwargs

        def warning(self, *args, **kwargs) -> None:
            del args, kwargs

        def debug(self, *args, **kwargs) -> None:
            del args, kwargs

        def error(self, *args, **kwargs) -> None:
            del args, kwargs

        def exception(self, *args, **kwargs) -> None:
            del args, kwargs

    fake_structlog.get_logger = lambda *args, **kwargs: DummyLogger()
    sys.modules["structlog"] = fake_structlog


if "pandas_market_calendars" not in sys.modules:
    fake_market_calendars = types.ModuleType("pandas_market_calendars")

    def _parse_schedule_date(value: str | date | datetime) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    class FakeSchedule:
        def __init__(self, trading_days: list[datetime]) -> None:
            self.index = trading_days

        @property
        def empty(self) -> bool:
            return not self.index

    class FakeCalendar:
        def schedule(self, start_date, end_date) -> FakeSchedule:
            current = _parse_schedule_date(start_date)
            end = _parse_schedule_date(end_date)
            trading_days: list[datetime] = []
            while current <= end:
                if current.weekday() < 5:
                    trading_days.append(datetime.combine(current, datetime.min.time()))
                    break
                current += timedelta(days=1)
            return FakeSchedule(trading_days)

    fake_market_calendars.get_calendar = lambda name: FakeCalendar()
    sys.modules["pandas_market_calendars"] = fake_market_calendars


class SyncAsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement, *args, **kwargs):
        return self._session.execute(statement, *args, **kwargs)

    async def get(self, model, ident):
        return self._session.get(model, ident)

    def add(self, instance) -> None:
        self._session.add(instance)

    def add_all(self, instances) -> None:
        self._session.add_all(instances)

    async def flush(self) -> None:
        self._session.flush()

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def delete(self, instance) -> None:
        self._session.delete(instance)


def _build_sqlite_insert_with_ids(sync_session: Session):
    next_ids: dict[str, int] = {}

    def _resolve_table(target):
        return getattr(target, "__table__", target)

    def _next_id(table_name: str, column) -> int:
        cached = next_ids.get(table_name)
        if cached is None:
            with sync_session.no_autoflush:
                db_max = sync_session.execute(select(func.max(column))).scalar_one_or_none() or 0
            cached = int(db_max) + 1
        next_ids[table_name] = cached + 1
        return cached

    class InsertProxy:
        def __init__(self, table) -> None:
            self._table = _resolve_table(table)
            self._stmt = sqlite_insert(self._table)

        def values(self, rows):
            normalized_rows = rows
            if isinstance(rows, dict):
                normalized_rows = [rows]

            rows_with_ids = []
            for row in normalized_rows:
                row_dict = dict(row)
                if "id" in self._table.c and row_dict.get("id") is None:
                    row_dict["id"] = _next_id(self._table.name, self._table.c.id)
                rows_with_ids.append(row_dict)

            self._stmt = self._stmt.values(rows_with_ids)
            return self

        def on_conflict_do_update(self, *args, **kwargs):
            return self._stmt.on_conflict_do_update(*args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._stmt, item)

    def _factory(table):
        return InsertProxy(table)

    return _factory


@dataclass
class TestDb:
    session: SyncAsyncSessionAdapter
    sync_session: Session


@pytest.fixture
def test_db() -> Iterator[TestDb]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    sync_session = session_factory()
    id_counters: dict[str, int] = {}

    @event.listens_for(sync_session, "before_flush")
    def assign_bigint_ids(session: Session, flush_context, instances) -> None:
        del flush_context, instances
        for obj in session.new:
            if not hasattr(obj, "id") or getattr(obj, "id", None) is not None:
                continue
            table_name = obj.__class__.__tablename__
            id_counters[table_name] = id_counters.get(table_name, 0) + 1
            obj.id = id_counters[table_name]

    db_service_module = importlib.import_module("app.service.db_service")
    original_insert = db_service_module.pg_insert
    db_service_module.pg_insert = _build_sqlite_insert_with_ids(sync_session)

    try:
        yield TestDb(
            session=SyncAsyncSessionAdapter(sync_session),
            sync_session=sync_session,
        )
    finally:
        db_service_module.pg_insert = original_insert
        sync_session.close()
        engine.dispose()


@pytest.fixture
def stocks_router_module(monkeypatch: pytest.MonkeyPatch):
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = lambda rows: rows
    monkeypatch.setitem(sys.modules, "pandas", fake_pandas)

    fake_technical = types.ModuleType("app.analysis.technical")
    fake_technical.calculate_technical_indicators = lambda dataframe: {"stub": True}
    monkeypatch.setitem(sys.modules, "app.analysis.technical", fake_technical)

    fake_runner = types.ModuleType("app.analysis.claude_runner")

    class DummyClaudeRunner:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def run(self, prompt: str) -> dict:
            del prompt
            return {}

    fake_runner.ClaudeRunner = DummyClaudeRunner
    monkeypatch.setitem(sys.modules, "app.analysis.claude_runner", fake_runner)

    fake_prompts = types.ModuleType("app.analysis.prompts")
    fake_prompts.build_analysis_prompt = lambda **kwargs: "prompt"
    monkeypatch.setitem(sys.modules, "app.analysis.prompts", fake_prompts)

    fake_session_module = types.ModuleType("app.database.session")

    class DummyAsyncSessionFactory:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    async def fake_get_db():
        yield None

    fake_session_module.async_session_factory = DummyAsyncSessionFactory()
    fake_session_module.get_db = fake_get_db
    monkeypatch.setitem(sys.modules, "app.database.session", fake_session_module)

    sys.modules.pop("app.routers.stocks", None)
    return importlib.import_module("app.routers.stocks")


@pytest.fixture
def portfolio_router_module(monkeypatch: pytest.MonkeyPatch):
    fake_session_module = types.ModuleType("app.database.session")

    async def fake_get_db():
        yield None

    fake_session_module.get_db = fake_get_db
    monkeypatch.setitem(sys.modules, "app.database.session", fake_session_module)

    sys.modules.pop("app.routers.portfolio", None)
    return importlib.import_module("app.routers.portfolio")


@pytest.fixture
def screener_router_module(monkeypatch: pytest.MonkeyPatch):
    fake_session_module = types.ModuleType("app.database.session")

    async def fake_get_db():
        yield None

    fake_session_module.get_db = fake_get_db
    monkeypatch.setitem(sys.modules, "app.database.session", fake_session_module)

    sys.modules.pop("app.routers.screener", None)
    return importlib.import_module("app.routers.screener")


@pytest.fixture
def jobs_module(monkeypatch: pytest.MonkeyPatch):
    fake_analyzer = types.ModuleType("app.analysis.analyzer")
    fake_analyzer.run_multi_analysis = lambda *args, **kwargs: None
    fake_analyzer.run_stock_analysis = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.analysis.analyzer", fake_analyzer)

    fake_accuracy = types.ModuleType("app.analysis.accuracy")

    async def fake_evaluate_past_analyses(*args, **kwargs):
        del args, kwargs
        return {}

    fake_accuracy.evaluate_past_analyses = fake_evaluate_past_analyses
    monkeypatch.setitem(sys.modules, "app.analysis.accuracy", fake_accuracy)

    fake_reflection = types.ModuleType("app.analysis.reflection")
    fake_reflection.run_weekly_reflection = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.analysis.reflection", fake_reflection)

    fake_runner = types.ModuleType("app.analysis.claude_runner")
    fake_runner.ClaudeRunner = object
    monkeypatch.setitem(sys.modules, "app.analysis.claude_runner", fake_runner)

    fake_sentiment = types.ModuleType("app.analysis.sentiment")
    fake_sentiment.analyze_sentiment_batch = lambda *args, **kwargs: []
    fake_sentiment.update_news_sentiment = lambda *args, **kwargs: 0
    monkeypatch.setitem(sys.modules, "app.analysis.sentiment", fake_sentiment)

    fake_technical = types.ModuleType("app.analysis.technical")
    fake_technical.calculate_technical_indicators = lambda dataframe: {"stub": True}
    monkeypatch.setitem(sys.modules, "app.analysis.technical", fake_technical)

    fake_dart = types.ModuleType("app.collectors.dart_collector")
    fake_dart.collect_today_disclosures = lambda *args, **kwargs: []
    fake_dart.collect_fundamentals_for_watchlist = lambda *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "app.collectors.dart_collector", fake_dart)

    fake_krx = types.ModuleType("app.collectors.krx_collector")
    fake_krx.collect_krx_index_ohlcv = lambda *args, **kwargs: []
    fake_krx.collect_krx_ohlcv = lambda *args, **kwargs: []
    fake_krx.collect_investor_trading = lambda *args, **kwargs: []
    fake_krx.collect_stock_listing = lambda *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "app.collectors.krx_collector", fake_krx)

    fake_news = types.ModuleType("app.collectors.news_collector")
    fake_news.collect_rss_news = lambda *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "app.collectors.news_collector", fake_news)

    fake_us = types.ModuleType("app.collectors.us_collector")
    fake_us.collect_us_ohlcv = lambda *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "app.collectors.us_collector", fake_us)

    fake_config = types.ModuleType("app.core.config")

    class DummySettings:
        KR_WATCHLIST: list[str] = []
        US_WATCHLIST: list[str] = []
        CLAUDE_PATH = "claude"
        CLAUDE_TIMEOUT = 30

    fake_config.settings = DummySettings()
    monkeypatch.setitem(sys.modules, "app.core.config", fake_config)

    fake_session_module = types.ModuleType("app.database.session")

    class DummyAsyncSessionFactory:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    fake_session_module.async_session_factory = DummyAsyncSessionFactory()
    monkeypatch.setitem(sys.modules, "app.database.session", fake_session_module)

    fake_db_service = types.ModuleType("app.service.db_service")
    fake_db_service.bulk_insert_daily_prices = lambda *args, **kwargs: 0
    fake_db_service.get_daily_prices = lambda *args, **kwargs: []
    fake_db_service.get_recent_news = lambda *args, **kwargs: []
    fake_db_service.get_stock_by_ticker = lambda *args, **kwargs: None
    fake_db_service.get_stock_id_map = lambda *args, **kwargs: {}
    fake_db_service.get_stock_name_map = lambda *args, **kwargs: {}
    fake_db_service.ensure_benchmark_stocks = lambda *args, **kwargs: None
    fake_db_service.log_collection = lambda *args, **kwargs: None
    fake_db_service.refresh_news_observed_reactions = lambda *args, **kwargs: 0
    fake_db_service.save_analysis_report = lambda *args, **kwargs: None
    fake_db_service.sync_configured_us_watchlist_stocks = lambda *args, **kwargs: 0
    fake_db_service.upsert_news_articles = lambda *args, **kwargs: 0
    fake_db_service.upsert_stocks = lambda *args, **kwargs: 0
    monkeypatch.setitem(sys.modules, "app.service.db_service", fake_db_service)

    fake_alerting = types.ModuleType("app.utils.alerting")
    fake_alerting.notify_failure = lambda *args, **kwargs: None
    fake_alerting.notify_success = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.utils.alerting", fake_alerting)

    fake_market_calendar = types.ModuleType("app.utils.market_calendar")
    fake_market_calendar.is_krx_trading_day = lambda: True
    fake_market_calendar.is_nyse_trading_day = lambda: True
    monkeypatch.setitem(sys.modules, "app.utils.market_calendar", fake_market_calendar)

    fake_discord = types.ModuleType("app.utils.discord")
    fake_discord.send_analysis_alert = lambda *args, **kwargs: None
    fake_discord.send_market_summary = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.utils.discord", fake_discord)

    sys.modules.pop("app.scheduler.jobs", None)
    return importlib.import_module("app.scheduler.jobs")
