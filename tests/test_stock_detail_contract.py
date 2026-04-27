from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database.models import AnalysisReport, DailyPrice, Stock
from app.service.db_service import get_daily_prices


async def test_get_daily_prices_returns_ascending_order_after_desc_query_reverse(test_db) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    test_db.session.add_all(
        [
            stock,
            DailyPrice(
                id=10,
                stock_id=stock.id,
                trade_date=date(2026, 4, 24),
                open=Decimal("100.00"),
                high=Decimal("110.00"),
                low=Decimal("99.00"),
                close=Decimal("105.00"),
                volume=1000,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                id=11,
                stock_id=stock.id,
                trade_date=date(2026, 4, 22),
                open=Decimal("90.00"),
                high=Decimal("95.00"),
                low=Decimal("85.00"),
                close=Decimal("92.00"),
                volume=900,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                id=12,
                stock_id=stock.id,
                trade_date=date(2026, 4, 23),
                open=Decimal("95.00"),
                high=Decimal("99.00"),
                low=Decimal("91.00"),
                close=Decimal("96.00"),
                volume=950,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
        ]
    )
    await test_db.session.flush()

    prices = await get_daily_prices(test_db.session, stock.id, limit=3)

    assert [str(price.trade_date) for price in prices] == [
        "2026-04-22",
        "2026-04-23",
        "2026-04-24",
    ]
    assert prices[-1].close == 105


async def test_get_daily_prices_returns_empty_list_when_stock_has_no_prices(test_db) -> None:
    stock = Stock(id=1, ticker="000660", name="SK하이닉스", market="KRX", sector="IT")
    test_db.session.add(stock)
    await test_db.session.flush()

    prices = await get_daily_prices(test_db.session, stock.id, limit=5)

    assert prices == []


async def test_stock_detail_returns_empty_sections_when_prices_analysis_and_news_are_missing(
    test_db,
    stocks_router_module,
) -> None:
    stock = Stock(id=1, ticker="035420", name="NAVER", market="KRX", sector="인터넷")
    test_db.session.add(stock)
    await test_db.session.flush()

    response = await stocks_router_module.get_stock_detail(stock.ticker, test_db.session)

    assert response == {
        "stock": {
            "ticker": "035420",
            "name": "NAVER",
            "market": "KRX",
            "sector": "인터넷",
        },
        "prices": [],
        "latest_price": None,
        "analysis": None,
        "news": [],
        "technical": None,
    }


async def test_stock_detail_returns_explicit_latest_price_and_daily_analysis_only(
    test_db,
    stocks_router_module,
) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="IT")
    daily_report = AnalysisReport(
        stock_id=1,
        analysis_date=date(2026, 4, 24),
        analysis_type="daily",
        summary="final daily report",
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
        summary="newer but not final daily",
        recommendation="hold",
        confidence=Decimal("0.55"),
        target_price=Decimal("70000.00"),
        key_factors={"a": "on-demand"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude",
    )
    test_db.session.add_all(
        [
            stock,
            DailyPrice(
                id=10,
                stock_id=stock.id,
                trade_date=date(2026, 4, 24),
                open=Decimal("100.00"),
                high=Decimal("110.00"),
                low=Decimal("99.00"),
                close=Decimal("105.00"),
                volume=1000,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                id=11,
                stock_id=stock.id,
                trade_date=date(2026, 4, 22),
                open=Decimal("90.00"),
                high=Decimal("95.00"),
                low=Decimal("85.00"),
                close=Decimal("92.00"),
                volume=900,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            DailyPrice(
                id=12,
                stock_id=stock.id,
                trade_date=date(2026, 4, 23),
                open=Decimal("95.00"),
                high=Decimal("99.00"),
                low=Decimal("91.00"),
                close=Decimal("96.00"),
                volume=950,
                market_cap=None,
                foreign_ratio=None,
                inst_net_buy=None,
                foreign_net_buy=None,
            ),
            daily_report,
            on_demand_report,
        ]
    )
    await test_db.session.flush()

    response = await stocks_router_module.get_stock_detail(stock.ticker, test_db.session)

    assert [price["trade_date"] for price in response["prices"]] == [
        "2026-04-22",
        "2026-04-23",
        "2026-04-24",
    ]
    assert response["latest_price"] == {
        "trade_date": "2026-04-24",
        "open": 100.0,
        "high": 110.0,
        "low": 99.0,
        "close": 105.0,
        "volume": 1000,
    }
    assert response["analysis"] is not None
    assert response["analysis"]["analysis_type"] == "daily"
    assert response["analysis"]["analysis_date"] == "2026-04-24"
    assert response["analysis"]["summary"] == "final daily report"
