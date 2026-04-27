from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.database.models import DailyPrice, Stock


async def test_portfolio_summary_handles_empty_portfolio(test_db, portfolio_router_module) -> None:
    summary = await portfolio_router_module.get_portfolio_summary(test_db.session)

    assert summary == {
        "invested_amount": 0.0,
        "latest_valuation": 0.0,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_percent": None,
        "has_missing_prices": False,
        "has_mixed_currencies": False,
        "currency_breakdown": [],
        "holdings": [],
        "allocation": [],
    }


async def test_portfolio_create_list_update_delete_holding_flow(
    test_db,
    portfolio_router_module,
) -> None:
    test_db.session.add_all(
        [
            Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT"),
            Stock(id=2, ticker="AAPL", name="Apple", market="NASDAQ", sector="Technology"),
        ]
    )
    await test_db.session.flush()

    samsung = await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="005930",
            quantity=Decimal("10"),
            average_price=Decimal("70000"),
        ),
        test_db.session,
    )
    apple = await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="AAPL",
            quantity=Decimal("2"),
            average_price=Decimal("150"),
        ),
        test_db.session,
    )

    listed = await portfolio_router_module.list_portfolio_holdings(test_db.session)

    assert [holding["ticker"] for holding in listed["holdings"]] == ["005930", "AAPL"]
    assert samsung["currency"] == "KRW"
    assert apple["currency"] == "USD"
    assert samsung["is_price_missing"] is True
    assert samsung["latest_price"] is None

    updated = await portfolio_router_module.update_portfolio_holding(
        samsung["id"],
        portfolio_router_module.PortfolioHoldingUpdateRequest(
            quantity=Decimal("12"),
            average_price=Decimal("71000"),
        ),
        test_db.session,
    )

    assert updated["quantity"] == 12.0
    assert updated["average_price"] == 71000.0

    deleted = await portfolio_router_module.delete_portfolio_holding(apple["id"], test_db.session)

    assert deleted == {"deleted": True, "holding_id": apple["id"]}

    listed_after_delete = await portfolio_router_module.list_portfolio_holdings(test_db.session)

    assert [holding["ticker"] for holding in listed_after_delete["holdings"]] == ["005930"]


async def test_portfolio_summary_uses_latest_known_daily_prices(
    test_db,
    portfolio_router_module,
) -> None:
    samsung = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    apple = Stock(id=2, ticker="AAPL", name="Apple", market="NASDAQ", sector="Technology")
    test_db.session.add_all(
        [
            samsung,
            apple,
            DailyPrice(
                stock_id=1,
                trade_date=date(2026, 4, 24),
                open=Decimal("69000.00"),
                high=Decimal("71500.00"),
                low=Decimal("68900.00"),
                close=Decimal("71000.00"),
                volume=1000,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                stock_id=1,
                trade_date=date(2026, 4, 25),
                open=Decimal("70000.00"),
                high=Decimal("72500.00"),
                low=Decimal("69900.00"),
                close=Decimal("72000.00"),
                volume=1100,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                stock_id=2,
                trade_date=date(2026, 4, 24),
                open=Decimal("155.00"),
                high=Decimal("160.00"),
                low=Decimal("154.00"),
                close=Decimal("160.00"),
                volume=2000,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
        ]
    )
    await test_db.session.flush()

    await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="005930",
            quantity=Decimal("10"),
            average_price=Decimal("70000"),
        ),
        test_db.session,
    )
    await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="AAPL",
            quantity=Decimal("2"),
            average_price=Decimal("150"),
        ),
        test_db.session,
    )

    summary = await portfolio_router_module.get_portfolio_summary(test_db.session)

    assert summary["invested_amount"] is None
    assert summary["latest_valuation"] is None
    assert summary["unrealized_pnl"] is None
    assert summary["unrealized_pnl_percent"] is None
    assert summary["has_missing_prices"] is False
    assert summary["has_mixed_currencies"] is True
    assert summary["currency_breakdown"] == [
        {
            "currency": "KRW",
            "invested_amount": 700000.0,
            "latest_valuation": 720000.0,
            "unrealized_pnl": 20000.0,
            "unrealized_pnl_percent": pytest.approx(2.86, abs=0.01),
            "has_missing_prices": False,
        },
        {
            "currency": "USD",
            "invested_amount": 300.0,
            "latest_valuation": 320.0,
            "unrealized_pnl": 20.0,
            "unrealized_pnl_percent": pytest.approx(6.67, abs=0.01),
            "has_missing_prices": False,
        },
    ]
    assert summary["allocation"] == [
        {
            "holding_id": 1,
            "ticker": "005930",
            "name": "삼성전자",
            "market": "KRX",
            "currency": "KRW",
            "latest_valuation": 720000.0,
            "allocation_percent": None,
            "is_price_missing": False,
        },
        {
            "holding_id": 2,
            "ticker": "AAPL",
            "name": "Apple",
            "market": "NASDAQ",
            "currency": "USD",
            "latest_valuation": 320.0,
            "allocation_percent": None,
            "is_price_missing": False,
        },
    ]


async def test_portfolio_summary_marks_missing_latest_price_without_fabricating_valuation(
    test_db,
    portfolio_router_module,
) -> None:
    test_db.session.add_all(
        [
            Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT"),
            Stock(id=2, ticker="AAPL", name="Apple", market="NASDAQ", sector="Technology"),
            DailyPrice(
                stock_id=1,
                trade_date=date(2026, 4, 25),
                open=Decimal("70000.00"),
                high=Decimal("72500.00"),
                low=Decimal("69900.00"),
                close=Decimal("72000.00"),
                volume=1100,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
        ]
    )
    await test_db.session.flush()

    await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="005930",
            quantity=Decimal("10"),
            average_price=Decimal("70000"),
        ),
        test_db.session,
    )
    await portfolio_router_module.create_portfolio_holding(
        portfolio_router_module.PortfolioHoldingCreateRequest(
            ticker="AAPL",
            quantity=Decimal("2"),
            average_price=Decimal("150"),
        ),
        test_db.session,
    )

    summary = await portfolio_router_module.get_portfolio_summary(test_db.session)

    assert summary["has_missing_prices"] is True
    assert summary["latest_valuation"] is None
    assert summary["unrealized_pnl"] is None
    assert summary["unrealized_pnl_percent"] is None
    assert summary["holdings"][1]["ticker"] == "AAPL"
    assert summary["holdings"][1]["is_price_missing"] is True
    assert summary["holdings"][1]["latest_price"] is None
    assert summary["holdings"][1]["latest_valuation"] is None
    assert summary["holdings"][1]["allocation_percent"] is None


async def test_portfolio_create_rejects_unknown_ticker(test_db, portfolio_router_module) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await portfolio_router_module.create_portfolio_holding(
            portfolio_router_module.PortfolioHoldingCreateRequest(
                ticker="MSFT",
                quantity=Decimal("1"),
                average_price=Decimal("300"),
            ),
            test_db.session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "종목을 찾을 수 없습니다: MSFT"
