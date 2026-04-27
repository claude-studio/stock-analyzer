from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.database.models import AnalysisReport, Stock
from app.service import db_service


def _build_report(
    *,
    stock_id: int,
    analysis_date: date,
    analysis_type: str,
    summary: str,
    recommendation: str,
    confidence: str,
    target_price: str,
    created_at: datetime,
) -> AnalysisReport:
    return AnalysisReport(
        stock_id=stock_id,
        analysis_date=analysis_date,
        analysis_type=analysis_type,
        summary=summary,
        recommendation=recommendation,
        confidence=Decimal(confidence),
        target_price=Decimal(target_price),
        key_factors={"source": analysis_type},
        bull_case="bull",
        bear_case="bear",
        model_used="claude-daily",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_get_analysis_history_returns_daily_reports_only_in_descending_date_order(
    test_db,
) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    test_db.session.add(stock)

    test_db.session.add_all(
        [
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 23),
                analysis_type="daily",
                summary="older final daily",
                recommendation="hold",
                confidence="0.58",
                target_price="69000.00",
                created_at=datetime(2026, 4, 23, 16, 31, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 24),
                analysis_type="analyst_value",
                summary="internal analyst shard",
                recommendation="buy",
                confidence="0.80",
                target_price="72000.00",
                created_at=datetime(2026, 4, 24, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 24),
                analysis_type="daily",
                summary="latest final daily",
                recommendation="buy",
                confidence="0.71",
                target_price="71000.00",
                created_at=datetime(2026, 4, 24, 16, 32, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 25),
                analysis_type="on_demand",
                summary="intraday refresh should stay hidden",
                recommendation="sell",
                confidence="0.49",
                target_price="68000.00",
                created_at=datetime(2026, 4, 25, 9, 5, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
        ]
    )
    await test_db.session.flush()

    history_loader = getattr(db_service, "get_analysis_history", None)
    assert history_loader is not None, "get_analysis_history helper must exist"

    history = await history_loader(test_db.session, stock.id)

    assert [report.analysis_type for report in history] == ["daily", "daily"]
    assert [str(report.analysis_date) for report in history] == [
        "2026-04-24",
        "2026-04-23",
    ]
    assert [report.summary for report in history] == [
        "latest final daily",
        "older final daily",
    ]


@pytest.mark.asyncio
async def test_stock_analysis_history_endpoint_returns_user_facing_daily_rows_only(
    test_db,
    stocks_router_module,
) -> None:
    stock = Stock(id=1, ticker="000660", name="SK하이닉스", market="KRX", sector="반도체")
    test_db.session.add(stock)

    test_db.session.add_all(
        [
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 21),
                analysis_type="daily",
                summary="final daily 1",
                recommendation="hold",
                confidence="0.53",
                target_price="205000.00",
                created_at=datetime(2026, 4, 21, 16, 35, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 22),
                analysis_type="daily",
                summary="final daily 2",
                recommendation="buy",
                confidence="0.67",
                target_price="212000.00",
                created_at=datetime(2026, 4, 22, 16, 34, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
            _build_report(
                stock_id=stock.id,
                analysis_date=date(2026, 4, 22),
                analysis_type="analyst_momentum",
                summary="hidden shard",
                recommendation="buy",
                confidence="0.76",
                target_price="214000.00",
                created_at=datetime(2026, 4, 22, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")),
            ),
        ]
    )
    await test_db.session.flush()

    endpoint = getattr(stocks_router_module, "get_stock_analysis_history", None)
    assert endpoint is not None, "history route handler must exist"

    response = await endpoint(stock.ticker, test_db.session)

    assert response == {
        "ticker": "000660",
        "history": [
            {
                "analysis_date": "2026-04-22",
                "analysis_type": "daily",
                "summary": "final daily 2",
                "recommendation": "buy",
                "confidence": 0.67,
                "target_price": 212000.0,
                "key_factors": {"source": "daily"},
                "bull_case": "bull",
                "bear_case": "bear",
                "model_used": "claude-daily",
                "created_at": "2026-04-22 16:34:00",
            },
            {
                "analysis_date": "2026-04-21",
                "analysis_type": "daily",
                "summary": "final daily 1",
                "recommendation": "hold",
                "confidence": 0.53,
                "target_price": 205000.0,
                "key_factors": {"source": "daily"},
                "bull_case": "bull",
                "bear_case": "bear",
                "model_used": "claude-daily",
                "created_at": "2026-04-21 16:35:00",
            },
        ],
    }


@pytest.mark.asyncio
async def test_stock_analysis_history_endpoint_returns_empty_list_when_no_daily_history_exists(
    test_db,
    stocks_router_module,
) -> None:
    stock = Stock(id=1, ticker="035720", name="카카오", market="KRX", sector="인터넷")
    on_demand_only = _build_report(
        stock_id=stock.id,
        analysis_date=date(2026, 4, 27),
        analysis_type="on_demand",
        summary="intraday only",
        recommendation="hold",
        confidence="0.51",
        target_price="42000.00",
        created_at=datetime(2026, 4, 27, 9, 10, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    test_db.session.add_all([stock, on_demand_only])
    await test_db.session.flush()

    endpoint = getattr(stocks_router_module, "get_stock_analysis_history", None)
    assert endpoint is not None, "history route handler must exist"

    response = await endpoint(stock.ticker, test_db.session)

    assert response == {"ticker": "035720", "history": []}
