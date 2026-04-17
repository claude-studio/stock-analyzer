"""DB 저장/조회 서비스 레이어."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AnalysisReport,
    CollectionLog,
    DailyPrice,
    NewsArticle,
    Stock,
)

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


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
        set_={"name": stmt.excluded.name, "market": stmt.excluded.market, "sector": stmt.excluded.sector},
    )
    result = await session.execute(stmt)
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

        if not _validate_ohlcv(open_val, high_val, low_val, close_val, volume_val):
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
    logger.info("analysis_report_saved", stock_id=stock_id, date=str(analysis_date), type=analysis_type)

    result_row = await session.execute(
        select(AnalysisReport).where(
            AnalysisReport.stock_id == stock_id,
            AnalysisReport.analysis_date == analysis_date,
            AnalysisReport.analysis_type == analysis_type,
        )
    )
    return result_row.scalar_one()


async def get_latest_analysis(
    session: AsyncSession,
    stock_id: int,
) -> AnalysisReport | None:
    """종목의 최신 분석 리포트 조회."""
    result = await session.execute(
        select(AnalysisReport)
        .where(AnalysisReport.stock_id == stock_id)
        .order_by(AnalysisReport.analysis_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
# Helpers
# ──────────────────────────────────────────────


def _validate_ohlcv(
    open_val: Decimal | None,
    high_val: Decimal | None,
    low_val: Decimal | None,
    close_val: Decimal | None,
    volume: int,
) -> bool:
    """OHLCV 데이터 유효성 검증. False면 skip."""
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
