"""DB 저장/조회 서비스 레이어."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analysis.news_impact import (
    ObservedReaction,
    benchmark_ticker_for_market,
    calculate_observed_reaction_from_prices,
    resolve_effective_trading_date,
)
from app.database.models import (
    AccuracyTracker,
    AnalysisReport,
    CollectionLog,
    DailyPrice,
    NewsArticle,
    NewsStockImpact,
    PortfolioHolding,
    Stock,
    StockRelation,
)

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")

US_MARKETS = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC", "US"}
KR_MARKETS = {"KRX", "KOSPI", "KOSDAQ", "KONEX"}


# ──────────────────────────────────────────────
# Stock 마스터
# ──────────────────────────────────────────────


async def upsert_stocks(session: AsyncSession, df: pd.DataFrame) -> int:
    """종목 마스터 upsert. DataFrame 컬럼: Code, Name, Market, Sector (FDR 형식).

    Returns:
        upsert된 행 수
    """
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        ticker = str(row.get("Code", row.get("Symbol", ""))).strip()
        if not ticker:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": str(row.get("Name", "")),
                "market": str(row.get("Market", "KRX")),
                "sector": str(row.get("Sector", "")) or None,
                "is_active": True,
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(Stock).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "name": stmt.excluded.name,
            "market": stmt.excluded.market,
            "sector": stmt.excluded.sector,
        },
    )
    await session.execute(stmt)
    await session.flush()
    logger.info("stocks_upserted", count=len(rows))
    return len(rows)


async def get_stock_by_ticker(session: AsyncSession, ticker: str) -> Stock | None:
    """종목코드로 Stock 조회."""
    result = await session.execute(select(Stock).where(Stock.ticker == ticker))
    return result.scalar_one_or_none()


async def get_stock_id_map(session: AsyncSession) -> dict[str, int]:
    """전체 종목 ticker -> id 매핑 딕셔너리."""
    result = await session.execute(select(Stock.ticker, Stock.id))
    return {row.ticker: row.id for row in result}


async def ensure_benchmark_stocks(session: AsyncSession) -> int:
    """뉴스 영향 계산에 필요한 대표 벤치마크 종목을 보장한다."""
    rows = [
        {"ticker": "KOSPI", "name": "KOSPI", "market": "KOSPI", "sector": "benchmark"},
        {"ticker": "KOSDAQ", "name": "KOSDAQ", "market": "KOSDAQ", "sector": "benchmark"},
        {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "US", "sector": "benchmark"},
    ]
    stmt = pg_insert(Stock).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "name": stmt.excluded.name,
            "market": stmt.excluded.market,
            "sector": stmt.excluded.sector,
            "is_active": True,
        },
    )
    await session.execute(stmt)
    await session.flush()
    return len(rows)


async def get_stock_name_map(session: AsyncSession) -> dict[str, int]:
    """전체 종목 {종목명: stock_id} + {ticker: stock_id} 합친 매핑 딕셔너리.

    뉴스 제목에서 종목명 기반 매칭에 사용한다.
    """
    result = await session.execute(select(Stock.name, Stock.ticker, Stock.id))
    merged: dict[str, int] = {}
    for row in result:
        merged[row.ticker] = row.id
        if row.name:
            merged[row.name] = row.id
    return merged


async def list_stocks(
    session: AsyncSession,
    market: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Stock], int]:
    """종목 목록 조회 (페이지네이션)."""
    query = select(Stock).where(Stock.is_active.is_(True))
    if market:
        query = query.where(Stock.market == market)

    from sqlalchemy import func as sa_func

    count_q = select(sa_func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    query = query.order_by(Stock.ticker).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all()), total


def get_market_currency(market: str) -> str:
    """시장 코드로 통화 메타데이터를 추론한다."""
    normalized = market.upper().strip()
    if normalized in KR_MARKETS:
        return "KRW"
    if normalized in US_MARKETS:
        return "USD"
    return normalized or "UNKNOWN"


async def list_portfolio_holdings(session: AsyncSession) -> list[PortfolioHolding]:
    """포트폴리오 보유 종목 목록 조회."""
    result = await session.execute(
        select(PortfolioHolding)
        .options(selectinload(PortfolioHolding.stock))
        .order_by(PortfolioHolding.id.asc())
    )
    return list(result.scalars().all())


async def get_portfolio_holding(session: AsyncSession, holding_id: int) -> PortfolioHolding | None:
    """ID로 포트폴리오 보유 종목 조회."""
    result = await session.execute(
        select(PortfolioHolding)
        .options(selectinload(PortfolioHolding.stock))
        .where(PortfolioHolding.id == holding_id)
    )
    return result.scalar_one_or_none()


async def get_portfolio_holding_by_stock_id(
    session: AsyncSession,
    stock_id: int,
) -> PortfolioHolding | None:
    """stock_id로 기존 포트폴리오 보유 종목 조회."""
    result = await session.execute(
        select(PortfolioHolding)
        .options(selectinload(PortfolioHolding.stock))
        .where(PortfolioHolding.stock_id == stock_id)
    )
    return result.scalar_one_or_none()


async def create_portfolio_holding(
    session: AsyncSession,
    stock: Stock,
    quantity: Decimal,
    average_price: Decimal,
) -> PortfolioHolding:
    """포트폴리오 보유 종목 생성."""
    holding = PortfolioHolding(
        stock_id=stock.id,
        market=stock.market,
        currency=get_market_currency(stock.market),
        quantity=quantity,
        average_price=average_price,
    )
    session.add(holding)
    await session.flush()
    return await get_portfolio_holding(session, holding.id)


async def update_portfolio_holding(
    session: AsyncSession,
    holding: PortfolioHolding,
    stock: Stock,
    quantity: Decimal,
    average_price: Decimal,
) -> PortfolioHolding:
    """포트폴리오 보유 종목 수정."""
    holding.stock_id = stock.id
    holding.market = stock.market
    holding.currency = get_market_currency(stock.market)
    holding.quantity = quantity
    holding.average_price = average_price
    await session.flush()
    return await get_portfolio_holding(session, holding.id)


async def delete_portfolio_holding(session: AsyncSession, holding: PortfolioHolding) -> None:
    """포트폴리오 보유 종목 삭제."""
    await session.delete(holding)
    await session.flush()


async def get_latest_daily_price(session: AsyncSession, stock_id: int) -> DailyPrice | None:
    """종목의 최신 일봉 종가를 조회한다."""
    result = await session.execute(
        select(DailyPrice)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.trade_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ──────────────────────────────────────────────
# DailyPrice
# ──────────────────────────────────────────────


async def bulk_insert_daily_prices(
    session: AsyncSession,
    df: pd.DataFrame,
    stock_id_map: dict[str, int],
    market: str = "KRX",
) -> int:
    """OHLCV DataFrame을 daily_prices에 bulk upsert.

    pykrx DataFrame 컬럼: 시가, 고가, 저가, 종가, 거래량 (index=ticker)
    yfinance DataFrame: Open, High, Low, Close, Volume (multi-index columns)
    """
    if df.empty:
        return 0

    # 직전 종가 조회 (급변동 검증용)
    prev_close_map: dict[int, Decimal] = {}
    stock_ids_in_df = [
        sid for t in df.index if (sid := stock_id_map.get(str(t)))
    ]
    if stock_ids_in_df:
        prev_stmt = (
            select(DailyPrice.stock_id, DailyPrice.close)
            .where(DailyPrice.stock_id.in_(stock_ids_in_df))
            .order_by(DailyPrice.trade_date.desc())
            .distinct(DailyPrice.stock_id)
        )
        prev_result = await session.execute(prev_stmt)
        for row in prev_result:
            prev_close_map[row.stock_id] = row.close

    rows = []
    for ticker, row in df.iterrows():
        stock_id = stock_id_map.get(str(ticker))
        if not stock_id:
            continue

        trade_date = row.get("date", date.today())
        if isinstance(trade_date, pd.Timestamp):
            trade_date = trade_date.date()

        open_val = _to_decimal(row.get("시가", row.get("Open", 0)))
        high_val = _to_decimal(row.get("고가", row.get("High", 0)))
        low_val = _to_decimal(row.get("저가", row.get("Low", 0)))
        close_val = _to_decimal(row.get("종가", row.get("Close", 0)))
        volume_val = int(row.get("거래량", row.get("Volume", 0)))

        prev_close = prev_close_map.get(stock_id)
        if not _validate_ohlcv(
            open_val, high_val, low_val, close_val, volume_val,
            prev_close=prev_close, ticker=str(ticker),
        ):
            logger.warning("invalid_ohlcv_skipped", ticker=str(ticker), date=str(trade_date))
            continue

        rows.append(
            {
                "stock_id": stock_id,
                "trade_date": trade_date,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": volume_val,
                "market_cap": _to_int(row.get("시가총액")),
                "foreign_ratio": _to_decimal(row.get("외국인비율")),
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(DailyPrice).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trade_date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "market_cap": stmt.excluded.market_cap,
        },
    )
    await session.execute(stmt)
    await session.flush()
    logger.info("daily_prices_upserted", count=len(rows), market=market)
    return len(rows)


async def get_daily_prices(
    session: AsyncSession,
    stock_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 60,
) -> list[DailyPrice]:
    """종목 일별 시세 조회."""
    query = select(DailyPrice).where(DailyPrice.stock_id == stock_id)
    if start_date:
        query = query.where(DailyPrice.trade_date >= start_date)
    if end_date:
        query = query.where(DailyPrice.trade_date <= end_date)
    query = query.order_by(DailyPrice.trade_date.desc()).limit(limit)
    result = await session.execute(query)
    prices = list(result.scalars().all())
    prices.reverse()  # DESC -> ASC: 기술적 지표 계산에 필요한 시계열 순서
    return prices


# ──────────────────────────────────────────────
# NewsArticle
# ──────────────────────────────────────────────


async def upsert_news_articles(
    session: AsyncSession,
    articles: list[dict],
    stock_id_map: dict[str, int] | None = None,
) -> int:
    """뉴스 기사 upsert (url 기준 중복 제거).

    stock_id_map이 주어지면 제목에서 종목을 매칭하여 stock_id를 설정한다.
    """
    if not articles:
        return 0

    matcher = None
    if stock_id_map:
        from app.utils.stock_matcher import StockMatcher

        matcher = StockMatcher(stock_id_map)

    rows = []
    for art in articles:
        url = (art.get("link") or "").strip()
        if not url:
            continue
        title = art.get("title", "")[:500]
        matched_stock_id = None
        if matcher:
            matched = matcher.match(title)
            if matched:
                matched_stock_id = matched[0]
        rows.append(
            {
                "title": title,
                "source": art.get("source", "unknown")[:50],
                "url": url,
                "published_at": _parse_datetime(art.get("published", art.get("collected_at"))),
                "stock_id": matched_stock_id,
                "sentiment_score": None,
                "sentiment_label": None,
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(NewsArticle).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
    await session.execute(stmt)
    await session.flush()
    logger.info("news_articles_upserted", count=len(rows))
    return len(rows)


async def save_news_impact(
    session: AsyncSession,
    news_article_id: int,
    stock_id: int,
    impact_direction: str,
    impact_score: float | None,
    reason: str | None,
) -> None:
    """뉴스-종목 영향 매핑 저장 (upsert)."""
    score_decimal = Decimal(str(round(impact_score, 3))) if impact_score is not None else None
    stmt = pg_insert(NewsStockImpact).values(
        news_article_id=news_article_id,
        stock_id=stock_id,
        impact_direction=impact_direction,
        impact_score=score_decimal,
        reason=reason[:500] if reason else None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["news_article_id", "stock_id"],
        set_={
            "impact_direction": stmt.excluded.impact_direction,
            "impact_score": stmt.excluded.impact_score,
            "reason": stmt.excluded.reason,
        },
    )
    await session.execute(stmt)


async def refresh_news_observed_reactions(
    session: AsyncSession,
    days: int = 90,
    dry_run: bool = False,
) -> dict[str, int]:
    """최근 뉴스 영향 매핑에 일봉 기준 관측 가격 반응을 보강한다."""
    cutoff = datetime.now(tz=KST) - timedelta(days=days)
    stmt = (
        select(NewsStockImpact, NewsArticle, Stock)
        .join(NewsArticle, NewsStockImpact.news_article_id == NewsArticle.id)
        .join(Stock, NewsStockImpact.stock_id == Stock.id)
        .where(NewsArticle.published_at >= cutoff)
        .order_by(NewsArticle.published_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    targets: list[tuple[NewsStockImpact, NewsArticle, Stock, date]] = []
    cluster_counts: dict[tuple[int, date], int] = {}
    for impact, article, stock in rows:
        effective_date = resolve_effective_trading_date(stock.market, article.published_at)
        targets.append((impact, article, stock, effective_date))
        key = (stock.id, effective_date)
        cluster_counts[key] = cluster_counts.get(key, 0) + 1

    updated = 0
    skipped = 0
    for impact, _article, stock, effective_date in targets:
        reaction, observed_windows = await _calculate_reaction_for_stock(
            session=session,
            stock=stock,
            effective_date=effective_date,
            confounded=cluster_counts[(stock.id, effective_date)] > 1,
        )
        if dry_run:
            skipped += 1
            continue
        await _update_observed_reaction(session, impact.id, reaction, observed_windows)
        updated += 1

    await session.flush()
    logger.info(
        "news_observed_reactions_refreshed",
        candidates=len(targets),
        updated=updated,
        dry_run=dry_run,
    )
    return {"candidates": len(targets), "updated": updated, "skipped": skipped}


async def _calculate_reaction_for_stock(
    *,
    session: AsyncSession,
    stock: Stock,
    effective_date: date,
    confounded: bool,
) -> tuple[ObservedReaction, list[dict]]:
    benchmark_ticker = benchmark_ticker_for_market(stock.market)
    benchmark = await get_stock_by_ticker(session, benchmark_ticker)
    start_date = effective_date - timedelta(days=5)
    end_date = effective_date + timedelta(days=14)
    stock_prices = await get_daily_prices(
        session,
        stock.id,
        start_date=start_date,
        end_date=end_date,
        limit=40,
    )
    benchmark_prices = []
    if benchmark:
        benchmark_prices = await get_daily_prices(
            session,
            benchmark.id,
            start_date=start_date,
            end_date=end_date,
            limit=40,
        )
    reactions = [
        calculate_observed_reaction_from_prices(
            stock_prices=stock_prices,
            benchmark_prices=benchmark_prices,
            market=stock.market,
            effective_date=effective_date,
            window_days=window_days,
            confounded=confounded,
        )
        for window_days in (1, 3)
    ]
    return reactions[0], [_serialize_reaction_window(reaction) for reaction in reactions]


async def _update_observed_reaction(
    session: AsyncSession,
    impact_id: int,
    reaction: ObservedReaction,
    observed_windows: list[dict],
) -> None:
    stmt = (
        update(NewsStockImpact)
        .where(NewsStockImpact.id == impact_id)
        .values(
            effective_trading_date=reaction.effective_trading_date,
            window_label=reaction.window_label,
            benchmark_ticker=reaction.benchmark_ticker,
            stock_return=reaction.stock_return,
            benchmark_return=reaction.benchmark_return,
            abnormal_return=reaction.abnormal_return,
            car=reaction.car,
            observed_windows=observed_windows,
            confidence=reaction.confidence,
            confounded=reaction.confounded,
            data_status=reaction.data_status,
            marker_label=reaction.marker_label,
        )
    )
    await session.execute(stmt)


async def get_news_impact_summary(
    session: AsyncSession,
    stock_id: int,
    days: int = 7,
) -> dict:
    """종목별 뉴스 영향 요약 (최근 N일)."""
    from datetime import timedelta

    cutoff = datetime.now(tz=KST) - timedelta(days=days)

    stmt = (
        select(
            NewsStockImpact,
            NewsArticle.title,
            NewsArticle.published_at,
            NewsArticle.url,
        )
        .join(NewsArticle, NewsStockImpact.news_article_id == NewsArticle.id)
        .options(selectinload(NewsStockImpact.stock))
        .where(
            NewsStockImpact.stock_id == stock_id,
            NewsArticle.published_at >= cutoff,
        )
        .order_by(NewsArticle.published_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    scores: list[float] = []
    recent_impacts: list[dict] = []

    for impact, title, published_at, url in rows:
        if impact.impact_direction == "bullish":
            bullish_count += 1
        elif impact.impact_direction == "bearish":
            bearish_count += 1
        else:
            neutral_count += 1

        if impact.impact_score is not None:
            scores.append(float(impact.impact_score))

        recent_impacts.append(_serialize_impact(impact, title=title, published_at=published_at))

    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "stock_id": stock_id,
        "days": days,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "total_count": len(rows),
        "total_news": len(rows),
        "avg_impact_score": round(avg_score, 3),
        "recent_impacts": recent_impacts[:10],
        "event_markers": recent_impacts[:50],
    }


async def get_news_detail(
    session: AsyncSession,
    news_id: int,
) -> dict | None:
    """뉴스 상세 조회 (영향 분석 포함)."""
    query = (
        select(NewsArticle)
        .outerjoin(Stock, NewsArticle.stock_id == Stock.id)
        .options(
            selectinload(NewsArticle.stock),
            selectinload(NewsArticle.stock_impacts).selectinload(NewsStockImpact.stock),
        )
        .where(NewsArticle.id == news_id)
    )
    result = await session.execute(query)
    article = result.scalar_one_or_none()
    if not article:
        return None

    return {
        "id": article.id,
        "title": article.title,
        "source": article.source,
        "url": article.url,
        "published_at": str(article.published_at) if article.published_at else None,
        "sentiment_score": (
            float(article.sentiment_score)
            if article.sentiment_score is not None
            else None
        ),
        "sentiment_label": article.sentiment_label,
        "news_category": article.news_category,
        "impact_summary": article.impact_summary,
        "sector": article.sector,
        "impact_score": float(article.impact_score) if article.impact_score is not None else None,
        "stock_ticker": article.stock.ticker if article.stock else None,
        "stock_name": article.stock.name if article.stock else None,
        "impacts": [
            _serialize_impact(imp)
            for imp in article.stock_impacts
        ],
    }


async def get_recent_news(
    session: AsyncSession,
    stock_id: int | None = None,
    limit: int = 20,
) -> list[NewsArticle]:
    """최근 뉴스 조회."""
    query = select(NewsArticle)
    if stock_id:
        query = query.where(NewsArticle.stock_id == stock_id)
    query = query.order_by(NewsArticle.published_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_recent_news_with_stock(
    session: AsyncSession,
    stock_id: int | None = None,
    ticker: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """뉴스 + 종목 정보 + 영향 분석 조인 조회."""
    query = (
        select(NewsArticle)
        .outerjoin(Stock, NewsArticle.stock_id == Stock.id)
        .options(
            selectinload(NewsArticle.stock),
            selectinload(NewsArticle.stock_impacts).selectinload(NewsStockImpact.stock),
        )
    )
    if stock_id:
        query = query.where(NewsArticle.stock_id == stock_id)
    elif ticker:
        query = query.where(Stock.ticker == ticker)
    query = query.order_by(NewsArticle.published_at.desc()).limit(limit)
    result = await session.execute(query)
    articles = list(result.scalars().all())
    return [
        {
            "id": a.id,
            "title": a.title,
            "source": a.source,
            "url": a.url,
            "published_at": str(a.published_at) if a.published_at else None,
            "sentiment_score": float(a.sentiment_score) if a.sentiment_score is not None else None,
            "sentiment_label": a.sentiment_label,
            "news_category": a.news_category,
            "impact_summary": a.impact_summary,
            "sector": a.sector,
            "stock_ticker": a.stock.ticker if a.stock else None,
            "stock_name": a.stock.name if a.stock else None,
            "impacts": [
                _serialize_impact(imp)
                for imp in a.stock_impacts
            ],
        }
        for a in articles
    ]


# ──────────────────────────────────────────────
# AnalysisReport
# ──────────────────────────────────────────────


async def save_analysis_report(
    session: AsyncSession,
    stock_id: int,
    analysis_date: date,
    analysis_type: str,
    result: dict,
    model_used: str = "claude-code-headless",
) -> AnalysisReport:
    """분석 리포트 저장 (upsert)."""
    stmt = pg_insert(AnalysisReport).values(
        stock_id=stock_id,
        analysis_date=analysis_date,
        analysis_type=analysis_type,
        summary=result.get("summary", ""),
        recommendation=result.get("recommendation"),
        confidence=_to_decimal(result.get("confidence")),
        target_price=_to_decimal(result.get("target_price")),
        key_factors=result.get("key_factors"),
        bull_case=result.get("bull_case"),
        bear_case=result.get("bear_case"),
        model_used=model_used,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="ix_analysis_reports_stock_date_type",
        set_={
            "summary": stmt.excluded.summary,
            "recommendation": stmt.excluded.recommendation,
            "confidence": stmt.excluded.confidence,
            "target_price": stmt.excluded.target_price,
            "key_factors": stmt.excluded.key_factors,
            "bull_case": stmt.excluded.bull_case,
            "bear_case": stmt.excluded.bear_case,
            "model_used": stmt.excluded.model_used,
        },
    )
    await session.execute(stmt)
    await session.flush()
    logger.info(
        "analysis_report_saved",
        stock_id=stock_id,
        date=str(analysis_date),
        type=analysis_type,
    )

    result_row = await session.execute(
        select(AnalysisReport).where(
            AnalysisReport.stock_id == stock_id,
            AnalysisReport.analysis_date == analysis_date,
            AnalysisReport.analysis_type == analysis_type,
        )
    )
    return result_row.scalar_one()


async def get_past_analyses(
    session: AsyncSession,
    days: int = 90,
) -> list[dict]:
    """최근 N일간 AnalysisReport + AccuracyTracker 조인하여 적중률 포함 결과 반환.

    Returns:
        [{"summary": str, "key_factors": list, "recommendation": str,
          "ticker": str, "hit_rate": float}, ...]
    """
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(
            AnalysisReport,
            Stock.ticker,
            AccuracyTracker.is_hit_7d,
        )
        .join(Stock, AnalysisReport.stock_id == Stock.id)
        .outerjoin(AccuracyTracker, AccuracyTracker.analysis_report_id == AnalysisReport.id)
        .where(AnalysisReport.analysis_date >= cutoff)
        .order_by(AnalysisReport.analysis_date.desc())
        .limit(500)
    )

    result = await session.execute(stmt)
    rows = result.all()

    reports: list[dict] = []
    for row in rows:
        report = row[0]
        ticker = row[1]
        is_hit = row[2]

        hit_rate = 0.5  # 기본값 (미평가)
        if is_hit is True:
            hit_rate = 1.0
        elif is_hit is False:
            hit_rate = 0.0

        key_factors = report.key_factors
        if isinstance(key_factors, dict):
            key_factors = list(key_factors.values()) if key_factors else []
        elif not isinstance(key_factors, list):
            key_factors = []

        reports.append({
            "summary": report.summary or "",
            "key_factors": key_factors,
            "recommendation": report.recommendation or "hold",
            "ticker": ticker,
            "hit_rate": hit_rate,
        })

    return reports


async def get_latest_analysis(
    session: AsyncSession,
    stock_id: int,
    analysis_type: str | None = "daily",
) -> AnalysisReport | None:
    """종목의 최신 분석 리포트 조회."""
    query = select(AnalysisReport).where(AnalysisReport.stock_id == stock_id)
    if analysis_type is not None:
        query = query.where(AnalysisReport.analysis_type == analysis_type)

    result = await session.execute(
        query
        .order_by(AnalysisReport.analysis_date.desc(), AnalysisReport.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_analysis_history(
    session: AsyncSession,
    stock_id: int,
    analysis_type: str | None = "daily",
) -> list[AnalysisReport]:
    """종목의 사용자 노출용 분석 리포트 히스토리 조회."""
    query = select(AnalysisReport).where(AnalysisReport.stock_id == stock_id)
    if analysis_type is not None:
        query = query.where(AnalysisReport.analysis_type == analysis_type)

    result = await session.execute(
        query.order_by(
            AnalysisReport.analysis_date.desc(),
            AnalysisReport.created_at.desc(),
        )
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# CollectionLog
# ──────────────────────────────────────────────


async def log_collection(
    session: AsyncSession,
    job_type: str,
    status: str,
    started_at: datetime,
    completed_at: datetime | None = None,
    target_date: date | None = None,
    stocks_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """수집 작업 로그 기록."""
    duration_ms = None
    if completed_at:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    log = CollectionLog(
        job_type=job_type,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        target_date=target_date,
        stocks_count=stocks_count,
        error_message=str(error_message)[:500] if error_message else None,
        duration_ms=duration_ms,
    )
    session.add(log)
    await session.flush()


# ──────────────────────────────────────────────
# StockRelation
# ──────────────────────────────────────────────


async def upsert_stock_relation(
    session: AsyncSession,
    source_stock_id: int,
    target_stock_id: int,
    relation_type: str,
    strength: float | None,
    context: str | None,
    source: str = "llm",
) -> None:
    """종목 관계 upsert."""
    strength_decimal = Decimal(str(round(strength, 3))) if strength is not None else None
    stmt = pg_insert(StockRelation).values(
        source_stock_id=source_stock_id,
        target_stock_id=target_stock_id,
        relation_type=relation_type,
        strength=strength_decimal,
        context=context[:500] if context else None,
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_stock_id", "relation_type", "target_stock_id"],
        set_={
            "strength": stmt.excluded.strength,
            "context": stmt.excluded.context,
            "source": stmt.excluded.source,
        },
    )
    await session.execute(stmt)


async def get_stock_relations(
    session: AsyncSession,
    stock_id: int,
) -> list[dict]:
    """종목의 모든 관계 조회."""
    stmt = (
        select(StockRelation, Stock.name, Stock.ticker)
        .join(Stock, StockRelation.target_stock_id == Stock.id)
        .where(StockRelation.source_stock_id == stock_id)
        .order_by(StockRelation.strength.desc().nulls_last())
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "target_ticker": ticker,
            "target_name": name,
            "relation_type": rel.relation_type,
            "strength": float(rel.strength) if rel.strength is not None else None,
            "context": rel.context,
            "source": rel.source,
            "updated_at": str(rel.updated_at) if rel.updated_at else None,
        }
        for rel, name, ticker in rows
    ]


async def get_all_watchlist_relations(
    session: AsyncSession,
    stock_ids: list[int],
) -> dict[int, list[dict]]:
    """워치리스트 전체 종목의 관계를 한번에 조회 (프롬프트 주입용)."""
    if not stock_ids:
        return {}

    stmt = (
        select(StockRelation, Stock.name, Stock.ticker)
        .join(Stock, StockRelation.target_stock_id == Stock.id)
        .where(StockRelation.source_stock_id.in_(stock_ids))
        .order_by(StockRelation.source_stock_id, StockRelation.strength.desc().nulls_last())
    )
    result = await session.execute(stmt)
    rows = result.all()

    relations_map: dict[int, list[dict]] = {}
    for rel, name, ticker in rows:
        entry = {
            "target_ticker": ticker,
            "target_name": name,
            "relation_type": rel.relation_type,
            "strength": float(rel.strength) if rel.strength is not None else None,
            "context": rel.context,
        }
        relations_map.setdefault(rel.source_stock_id, []).append(entry)

    return relations_map


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _validate_ohlcv(
    open_val: Decimal | None,
    high_val: Decimal | None,
    low_val: Decimal | None,
    close_val: Decimal | None,
    volume: int,
    prev_close: Decimal | None = None,
    ticker: str | None = None,
) -> bool:
    """OHLCV 데이터 유효성 검증. False면 skip.

    prev_close가 주어지면 전일 종가 대비 +/-50% 이상 변동 시
    액면분할 의심 warning 로그를 남긴다 (데이터 자체는 통과).
    """
    if any(v is None or v <= 0 for v in [open_val, high_val, low_val, close_val]):
        return False
    if volume < 0:
        return False
    if high_val < low_val:
        return False
    if open_val > high_val or open_val < low_val:
        return False
    if close_val > high_val or close_val < low_val:
        return False

    # 전일 대비 급변동 검증 (액면분할/무상증자 의심)
    if prev_close is not None and prev_close > 0 and close_val is not None:
        change_ratio = abs(float(close_val) - float(prev_close)) / float(prev_close)
        if change_ratio >= 0.5:
            logger.warning(
                "ohlcv_extreme_change_detected",
                ticker=ticker,
                prev_close=float(prev_close),
                close=float(close_val),
                change_pct=round(change_ratio * 100, 2),
                note="액면분할/무상증자 의심 - 수정주가 확인 필요",
            )
            # TODO: pykrx get_market_ohlcv_by_ticker는 수정주가 옵션 미지원.
            # 개별 종목 get_market_ohlcv_by_date(adjusted=True)로 보정하는
            # 별도 파이프라인 구현 필요.

    return True


def _to_decimal(val) -> Decimal | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return Decimal(str(val))


def _to_int(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return int(val)


def _parse_datetime(val) -> datetime:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return datetime.now(tz=KST)


def _serialize_impact(
    impact: NewsStockImpact,
    title: str | None = None,
    published_at: datetime | None = None,
) -> dict:
    return {
        "article_id": impact.news_article_id,
        "title": title,
        "stock_ticker": impact.stock.ticker if impact.stock else None,
        "stock_name": impact.stock.name if impact.stock else None,
        "impact_direction": impact.impact_direction,
        "impact_score": float(impact.impact_score) if impact.impact_score is not None else None,
        "reason": impact.reason,
        "published_at": str(published_at) if published_at else None,
        "effective_trading_date": str(impact.effective_trading_date)
        if impact.effective_trading_date
        else None,
        "window": impact.window_label,
        "benchmark": impact.benchmark_ticker,
        "stock_return": float(impact.stock_return) if impact.stock_return is not None else None,
        "benchmark_return": float(impact.benchmark_return)
        if impact.benchmark_return is not None
        else None,
        "abnormal_return": float(impact.abnormal_return)
        if impact.abnormal_return is not None
        else None,
        "car": float(impact.car) if impact.car is not None else None,
        "observed_windows": impact.observed_windows or [],
        "confidence": float(impact.confidence) if impact.confidence is not None else None,
        "confounded": impact.confounded,
        "data_status": impact.data_status,
        "marker_label": impact.marker_label,
    }


def _serialize_reaction_window(reaction: ObservedReaction) -> dict:
    return {
        "window": reaction.window_label,
        "benchmark": reaction.benchmark_ticker,
        "stock_return": float(reaction.stock_return) if reaction.stock_return is not None else None,
        "benchmark_return": (
            float(reaction.benchmark_return)
            if reaction.benchmark_return is not None
            else None
        ),
        "abnormal_return": (
            float(reaction.abnormal_return)
            if reaction.abnormal_return is not None
            else None
        ),
        "car": float(reaction.car) if reaction.car is not None else None,
        "confidence": float(reaction.confidence) if reaction.confidence is not None else None,
        "data_status": reaction.data_status,
    }
