from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.database.models import NewsArticle, NewsStockImpact, Stock
from app.service import db_service
from app.service.db_service import get_news_detail, get_news_impact_summary


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


async def test_get_news_impact_summary_returns_canonical_public_contract(
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

    assert summary["stock_id"] == 1
    assert summary["days"] == 7
    assert summary["bullish_count"] == 1
    assert summary["bearish_count"] == 0
    assert summary["neutral_count"] == 0
    assert summary["total_count"] == 1
    assert summary["avg_impact_score"] == 0.41
    assert "total_news" not in summary
    assert len(summary["recent_impacts"]) == 1
    assert len(summary["event_markers"]) == 1

    recent = summary["recent_impacts"][0]
    assert recent["title"] == "카카오 신규 서비스 확대"
    assert recent["impact_direction"] == "bullish"
    assert recent["impact_score"] == 0.41
    assert recent["reason"] == "신규 서비스 확장 기대"
    assert recent["published_at"] == "2026-04-27 10:00:00"
    assert recent["url"] == "https://example.com/news-1"
    assert "direction" not in recent
    assert "score" not in recent

    marker = summary["event_markers"][0]
    assert marker["impact_direction"] == "bullish"
    assert marker["impact_score"] == 0.41
    assert marker["url"] == "https://example.com/news-1"
    assert route_response["total_count"] == 1
    assert "total_news" not in route_response
    assert route_response["recent_impacts"][0]["impact_direction"] == "bullish"
    assert route_response["recent_impacts"][0]["impact_score"] == 0.41
    assert route_response["recent_impacts"][0]["url"] == "https://example.com/news-1"
    assert "direction" not in route_response["recent_impacts"][0]
    assert "score" not in route_response["recent_impacts"][0]


async def test_get_news_impact_summary_returns_zero_counts_when_no_impacts_exist(
    test_db,
    fixed_now: datetime,
) -> None:
    del fixed_now
    stock = Stock(id=1, ticker="068270", name="셀트리온", market="KRX", sector="제약")
    test_db.session.add(stock)
    await test_db.session.flush()

    summary = await get_news_impact_summary(test_db.session, stock.id, days=30)

    assert summary["stock_id"] == 1
    assert summary["days"] == 30
    assert summary["bullish_count"] == 0
    assert summary["bearish_count"] == 0
    assert summary["neutral_count"] == 0
    assert summary["total_count"] == 0
    assert summary["avg_impact_score"] == 0.0
    assert summary["recent_impacts"] == []
    assert summary["event_markers"] == []
    assert "total_news" not in summary


async def test_get_news_detail_keeps_article_url_and_canonical_impact_fields(
    test_db,
    fixed_now: datetime,
) -> None:
    stock = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="반도체")
    article = NewsArticle(
        stock_id=stock.id,
        title="삼성전자 AI 투자 확대",
        source="매일경제",
        url="https://example.com/news-2",
        published_at=fixed_now - timedelta(hours=1),
        sentiment_score=Decimal("0.120"),
        sentiment_label="positive",
        news_category="sector",
        impact_summary="AI 투자 확대 기대",
        sector="반도체",
        impact_score=Decimal("0.220"),
    )
    impact = NewsStockImpact(
        news_article_id=1,
        stock_id=1,
        impact_direction="bullish",
        impact_score=Decimal("0.220"),
        reason="AI 투자 수혜 기대",
    )
    test_db.session.add_all([stock, article, impact])
    await test_db.session.flush()

    detail = await get_news_detail(test_db.session, 1)

    assert detail is not None
    assert detail["url"] == "https://example.com/news-2"
    assert detail["impact_score"] == 0.22
    assert len(detail["impacts"]) == 1
    impact_payload = detail["impacts"][0]
    assert impact_payload["stock_ticker"] == "005930"
    assert impact_payload["stock_name"] == "삼성전자"
    assert impact_payload["impact_direction"] == "bullish"
    assert impact_payload["impact_score"] == 0.22
    assert impact_payload["reason"] == "AI 투자 수혜 기대"
    assert "direction" not in impact_payload
    assert "score" not in impact_payload
