from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.service import db_service
from app.service.db_service import (
    bulk_insert_daily_prices,
    get_daily_prices,
    get_stock_by_ticker,
    get_stock_id_map,
    list_stocks,
)


class SimpleFrame:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self._rows = rows
        self.index = list(rows.keys())

    @property
    def empty(self) -> bool:
        return not self._rows

    def iterrows(self):
        yield from self._rows.items()


async def test_sync_configured_us_watchlist_stocks_unblocks_aapl_price_persistence(
    test_db,
) -> None:
    seeded = await db_service.sync_configured_us_watchlist_stocks(
        test_db.session,
        [" aapl "],
    )

    stock = await get_stock_by_ticker(test_db.session, "AAPL")

    assert seeded == 1
    assert stock is not None
    assert stock.market == "US"
    assert stock.name

    stocks, total = await list_stocks(test_db.session, market="US", limit=10, offset=0)
    assert total == 1
    assert [item.ticker for item in stocks] == ["AAPL"]

    stock_id_map = await get_stock_id_map(test_db.session)
    inserted = await bulk_insert_daily_prices(
        test_db.session,
        SimpleFrame(
            {
                "AAPL": {
                    "Open": 171.25,
                    "High": 176.00,
                    "Low": 170.50,
                    "Close": 175.10,
                    "Volume": 1250000,
                    "date": date(2026, 4, 27),
                }
            }
        ),
        stock_id_map,
        market="US",
    )

    prices = await get_daily_prices(test_db.session, stock.id, limit=5)

    assert inserted == 1
    assert len(prices) == 1
    assert prices[0].close == Decimal("175.10")
