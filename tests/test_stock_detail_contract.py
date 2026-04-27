from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database.models import DailyPrice, Stock
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
        "analysis": None,
        "news": [],
        "technical": None,
    }
