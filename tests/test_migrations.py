"""Alembic migration safety tests."""

import importlib.util
from pathlib import Path
from types import ModuleType


class OperationRecorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def _load_migration(filename: str) -> ModuleType:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location("migration_under_test", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_observed_news_reaction_columns_migration_is_idempotent() -> None:
    migration = _load_migration("005_repair_observed_news_reaction_columns.py")
    recorder = OperationRecorder()
    migration.op = recorder

    migration.upgrade()

    sql = "\n".join(recorder.statements)
    expected_columns = [
        "effective_trading_date",
        "window_label",
        "benchmark_ticker",
        "stock_return",
        "benchmark_return",
        "abnormal_return",
        "car",
        "observed_windows",
        "confidence",
        "confounded",
        "data_status",
        "marker_label",
    ]
    for column in expected_columns:
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql
    assert "CREATE INDEX IF NOT EXISTS ix_news_stock_impacts_stock_effective_date" in sql
