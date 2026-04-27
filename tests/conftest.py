from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base

if "pandas" not in sys.modules:
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = lambda rows: rows
    fake_pandas.Series = object
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


class SyncAsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)

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

    try:
        yield TestDb(
            session=SyncAsyncSessionAdapter(sync_session),
            sync_session=sync_session,
        )
    finally:
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
