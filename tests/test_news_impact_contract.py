from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.database.models import NewsArticle, NewsStockImpact, Stock
from app.service import db_service
from app.service.db_service import get_news_impact_summary


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        current = cls(2026, 4, 27, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        if tz is None:
            return current.replace(tzinfo=None)
        return current.astimezone(tz)


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr(db_service, "datetime", FixedDateTime)
    return FixedDateTime.now(tz=ZoneInfo("Asia/Seoul"))


async def test_get_news_impact_summary_uses_current_backend_keys_and_reason_shape(
    test_db,
    stocks_router_module,
    fixed_now: datetime,
) -> None:
    stock = Stock(id=1, ticker="035720", name="카카오", market="KRX", sector="인터넷")
    article = NewsArticle(
        stock_id=stock.id,
        title="카카오 신규 서비스 확대",
        source="연합뉴스",
        url="https://example.com/news-1",
        published_at=fixed_now - timedelta(hours=2),
        sentiment_score=Decimal("0.330"),
        sentiment_label="positive",
        news_category="service",
        impact_summary="긍정",
        sector="인터넷",
        impact_score=Decimal("0.410"),
    )
    impact = NewsStockImpact(
        news_article_id=1,
        stock_id=1,
        impact_direction="bullish",
        impact_score=Decimal("0.410"),
        reason="신규 서비스 확장 기대",
    )
    test_db.session.add_all([stock, article, impact])
    await test_db.session.flush()

    summary = await get_news_impact_summary(test_db.session, stock.id, days=7)
    route_response = await stocks_router_module.get_stock_news_impact(
        stock.ticker,
        test_db.session,
        days=7,
    )

    assert summary == {
        "stock_id": 1,
        "days": 7,
        "bullish_count": 1,
        "bearish_count": 0,
        "neutral_count": 0,
        "total_count": 1,
        "avg_impact_score": 0.41,
        "recent_impacts": [
            {
                "title": "카카오 신규 서비스 확대",
                "direction": "bullish",
                "score": 0.41,
                "reason": "신규 서비스 확장 기대",
                "published_at": "2026-04-27 10:00:00",
            }
        ],
    }
    assert route_response["total_count"] == 1
    assert "total_news" not in route_response
    assert route_response["recent_impacts"][0]["direction"] == "bullish"
    assert "impact_direction" not in route_response["recent_impacts"][0]


async def test_get_news_impact_summary_returns_zero_counts_when_no_impacts_exist(
    test_db,
    fixed_now: datetime,
) -> None:
    del fixed_now
    stock = Stock(id=1, ticker="068270", name="셀트리온", market="KRX", sector="제약")
    test_db.session.add(stock)
    await test_db.session.flush()

    summary = await get_news_impact_summary(test_db.session, stock.id, days=30)

    assert summary == {
        "stock_id": 1,
        "days": 30,
        "bullish_count": 0,
        "bearish_count": 0,
        "neutral_count": 0,
        "total_count": 0,
        "avg_impact_score": 0.0,
        "recent_impacts": [],
    }
