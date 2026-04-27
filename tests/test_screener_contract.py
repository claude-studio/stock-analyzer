from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.database.models import AnalysisReport, DailyPrice, NewsArticle, NewsStockImpact, Stock

KST = ZoneInfo("Asia/Seoul")


def _build_price(
    *,
    stock_id: int,
    trade_date: date,
    close: str,
    volume: int,
    open: str | None = None,
) -> DailyPrice:
    open_value = open or close
    return DailyPrice(
        stock_id=stock_id,
        trade_date=trade_date,
        open=Decimal(open_value),
        high=Decimal(close),
        low=Decimal(open_value),
        close=Decimal(close),
        volume=volume,
        market_cap=None,
        foreign_ratio=None,
        inst_net_buy=None,
        foreign_net_buy=None,
    )


def _build_report(
    *,
    stock_id: int,
    analysis_date: date,
    recommendation: str,
    summary: str,
    confidence: str = "0.65",
) -> AnalysisReport:
    return AnalysisReport(
        stock_id=stock_id,
        analysis_date=analysis_date,
        analysis_type="daily",
        summary=summary,
        recommendation=recommendation,
        confidence=Decimal(confidence),
        target_price=Decimal("100000.00"),
        key_factors={"source": "daily"},
        bull_case="bull",
        bear_case="bear",
        model_used="claude-daily",
        created_at=datetime.combine(analysis_date, datetime.min.time(), tzinfo=KST),
    )


def _build_news(
    *,
    news_id: int,
    stock_id: int,
    title: str,
    published_at: datetime,
    sentiment_score: str,
) -> NewsArticle:
    return NewsArticle(
        id=news_id,
        stock_id=stock_id,
        title=title,
        source="한국경제",
        url=f"https://example.com/{news_id}",
        published_at=published_at,
        sentiment_score=Decimal(sentiment_score),
        sentiment_label="positive" if Decimal(sentiment_score) > 0 else "negative",
        news_category="earnings",
        impact_summary=title,
        sector="IT",
        impact_score=Decimal(sentiment_score),
    )


def _build_impact(
    *,
    impact_id: int,
    news_article_id: int,
    stock_id: int,
    impact_direction: str,
    impact_score: str,
    reason: str,
) -> NewsStockImpact:
    return NewsStockImpact(
        id=impact_id,
        news_article_id=news_article_id,
        stock_id=stock_id,
        impact_direction=impact_direction,
        impact_score=Decimal(impact_score),
        reason=reason,
    )


@pytest.mark.asyncio
async def test_screener_endpoint_ranks_krx_candidates_with_transparent_components(
    test_db,
    screener_router_module,
) -> None:
    samsung = Stock(id=1, ticker="005930", name="삼성전자", market="KRX", sector="반도체")
    hynix = Stock(id=2, ticker="000660", name="SK하이닉스", market="KOSPI", sector="반도체")
    apple = Stock(id=3, ticker="AAPL", name="Apple", market="US", sector="Technology")
    test_db.session.add_all([samsung, hynix, apple])

    test_db.session.add_all(
        [
            _build_price(stock_id=1, trade_date=date(2026, 4, 20), close="100.00", volume=1000),
            _build_price(stock_id=1, trade_date=date(2026, 4, 21), close="104.00", volume=1100),
            _build_price(stock_id=1, trade_date=date(2026, 4, 22), close="108.00", volume=1050),
            _build_price(stock_id=1, trade_date=date(2026, 4, 23), close="111.00", volume=1200),
            _build_price(stock_id=1, trade_date=date(2026, 4, 24), close="115.00", volume=2400),
            _build_price(stock_id=2, trade_date=date(2026, 4, 20), close="100.00", volume=1500),
            _build_price(stock_id=2, trade_date=date(2026, 4, 21), close="98.00", volume=1400),
            _build_price(stock_id=2, trade_date=date(2026, 4, 22), close="97.00", volume=1450),
            _build_price(stock_id=2, trade_date=date(2026, 4, 23), close="96.00", volume=1500),
            _build_price(stock_id=2, trade_date=date(2026, 4, 24), close="95.00", volume=1300),
            _build_price(stock_id=3, trade_date=date(2026, 4, 20), close="200.00", volume=5000),
            _build_price(stock_id=3, trade_date=date(2026, 4, 21), close="205.00", volume=5200),
            _build_price(stock_id=3, trade_date=date(2026, 4, 22), close="207.00", volume=5300),
            _build_price(stock_id=3, trade_date=date(2026, 4, 23), close="210.00", volume=5400),
            _build_price(stock_id=3, trade_date=date(2026, 4, 24), close="214.00", volume=5600),
            _build_report(
                stock_id=1,
                analysis_date=date(2026, 4, 24),
                recommendation="buy",
                summary="memory pricing and HBM upside",
            ),
            _build_report(
                stock_id=2,
                analysis_date=date(2026, 4, 24),
                recommendation="hold",
                summary="near-term volatility remains elevated",
            ),
            _build_news(
                news_id=101,
                stock_id=1,
                title="삼성전자 HBM 수주 확대",
                published_at=datetime(2026, 4, 23, 9, 0, tzinfo=KST),
                sentiment_score="0.45",
            ),
            _build_news(
                news_id=102,
                stock_id=1,
                title="삼성전자 AI 메모리 투자",
                published_at=datetime(2026, 4, 24, 8, 30, tzinfo=KST),
                sentiment_score="0.25",
            ),
            _build_news(
                news_id=201,
                stock_id=2,
                title="메모리 가격 변동성 확대",
                published_at=datetime(2026, 4, 24, 7, 45, tzinfo=KST),
                sentiment_score="-0.20",
            ),
            _build_impact(
                impact_id=1001,
                news_article_id=101,
                stock_id=1,
                impact_direction="bullish",
                impact_score="0.40",
                reason="HBM 수주 모멘텀",
            ),
            _build_impact(
                impact_id=1002,
                news_article_id=102,
                stock_id=1,
                impact_direction="bullish",
                impact_score="0.20",
                reason="AI 메모리 CAPEX 확대",
            ),
            _build_impact(
                impact_id=2001,
                news_article_id=201,
                stock_id=2,
                impact_direction="bearish",
                impact_score="-0.20",
                reason="단기 가격 변동성",
            ),
        ]
    )
    await test_db.session.flush()

    response = await screener_router_module.get_personal_screener(
        session=test_db.session,
        limit=10,
        lookback_days=30,
    )

    assert response["total_candidates"] == 2
    assert response["total_eligible"] == 2
    assert response["total_insufficient"] == 0
    assert response["coverage"] == {
        "ranked_markets": ["KRX", "KOSPI", "KOSDAQ", "KONEX"],
        "excluded_markets": ["US"],
        "uses_stored_data_only": True,
        "eligible_stocks": 2,
        "insufficient_stocks": 0,
    }
    assert response["reference_trade_date"] == "2026-04-24"
    assert "현재 DB에 저장된 데이터만 사용합니다." in response["limitations"]
    assert "미국 종목은 이 스크리너 랭킹에 포함하지 않습니다." in response["limitations"]

    candidates = response["candidates"]
    assert [candidate["ticker"] for candidate in candidates] == ["005930", "000660"]
    assert candidates[0]["score"] > candidates[1]["score"]

    top_candidate = candidates[0]
    assert top_candidate["name"] == "삼성전자"
    assert top_candidate["market"] == "KRX"
    assert top_candidate["latest_recommendation"] == "buy"
    assert top_candidate["analysis_date"] == "2026-04-24"
    assert top_candidate["latest_trade_date"] == "2026-04-24"
    assert top_candidate["latest_close"] == 115.0
    assert top_candidate["components"] == {
        "price_momentum_pct": 15.0,
        "price_momentum_score": 12.0,
        "volume_spike_ratio": 2.21,
        "volume_spike_score": 12.0,
        "recent_news_count": 2,
        "recent_news_score": 4.0,
        "avg_news_impact_score": 0.3,
        "news_impact_score": 3.6,
        "latest_daily_recommendation": "buy",
        "latest_daily_recommendation_score": 8.0,
    }
    assert top_candidate["reasons"] == [
        "최근 30일 종가가 +15.0% 움직였습니다.",
        "최신 거래량이 최근 평균의 2.21배입니다.",
        "최근 7일 관련 뉴스 2건이 저장돼 있습니다.",
        "최근 뉴스 영향 점수 평균은 +0.30입니다.",
        "최신 일일 리포트는 매수 의견입니다. (2026-04-24)",
    ]

    second_candidate = candidates[1]
    assert second_candidate["components"]["price_momentum_pct"] == -5.0
    assert second_candidate["components"]["avg_news_impact_score"] == -0.2
    assert second_candidate["reasons"][-1] == "최신 일일 리포트는 보유 의견입니다. (2026-04-24)"


@pytest.mark.asyncio
async def test_screener_endpoint_returns_empty_when_price_coverage_is_insufficient(
    test_db,
    screener_router_module,
) -> None:
    sparse = Stock(id=1, ticker="035420", name="NAVER", market="KRX", sector="인터넷")
    stale = Stock(id=2, ticker="051910", name="LG화학", market="KOSPI", sector="화학")
    test_db.session.add_all([sparse, stale])
    test_db.session.add_all(
        [
            _build_price(stock_id=1, trade_date=date(2026, 4, 23), close="200.00", volume=900),
            _build_price(stock_id=1, trade_date=date(2026, 4, 24), close="202.00", volume=950),
            _build_price(stock_id=2, trade_date=date(2026, 3, 1), close="300.00", volume=1200),
        ]
    )
    await test_db.session.flush()

    response = await screener_router_module.get_personal_screener(
        session=test_db.session,
        limit=10,
        lookback_days=30,
    )

    assert response["candidates"] == []
    assert response["total_candidates"] == 0
    assert response["total_eligible"] == 0
    assert response["total_insufficient"] == 2
    assert response["minimum_price_points"] == 5
    assert response["reference_trade_date"] == "2026-04-24"
    assert response["empty_state"] == {
        "title": "저장된 시세 커버리지가 아직 부족합니다.",
        "description": (
            "현재 저장된 KRX 가격·뉴스·일일 리포트 범위 안에서는 조건을 만족하는 "
            "후보를 계산하지 못했습니다. 기회가 없다는 뜻은 아닙니다."
        ),
    }
