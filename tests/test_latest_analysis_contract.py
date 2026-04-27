from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database.models import AnalysisReport, Stock
from app.service.db_service import get_latest_analysis


async def test_get_latest_analysis_returns_most_recent_report_even_when_it_is_not_daily(
    test_db,
) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    daily_report = AnalysisReport(
        stock_id=1,
        analysis_date=date(2026, 4, 24),
        analysis_type="daily",
        summary="daily baseline",
        recommendation="buy",
        confidence=Decimal("0.71"),
        target_price=Decimal("71000.00"),
        key_factors={"a": "daily"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    on_demand_report = AnalysisReport(
        stock_id=1,
        analysis_date=date(2026, 4, 27),
        analysis_type="on_demand",
        summary="picked because it is newer, not because it is daily",
        recommendation="hold",
        confidence=Decimal("0.55"),
        target_price=Decimal("70000.00"),
        key_factors={"a": "on-demand"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    test_db.session.add_all([stock, daily_report, on_demand_report])
    await test_db.session.flush()

    latest = await get_latest_analysis(test_db.session, stock.id)

    assert latest is not None
    assert latest.analysis_type == "on_demand"
    assert latest.analysis_date == date(2026, 4, 27)
    assert latest.summary == (
        "picked because it is newer, not because it is daily"
    )


async def test_stock_analysis_returns_none_when_no_report_exists(
    test_db,
    stocks_router_module,
) -> None:
    stock = Stock(id=1, ticker="051910", name="LG화학", market="KRX", sector="화학")
    test_db.session.add(stock)
    await test_db.session.flush()

    response = await stocks_router_module.get_stock_analysis(stock.ticker, test_db.session)

    assert response == {"ticker": "051910", "analysis": None}
