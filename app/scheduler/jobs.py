"""스케줄러 잡 함수 모듈."""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import select

from app.analysis.analyzer import run_stock_analysis
from app.analysis.claude_runner import ClaudeRunner
from app.database.models import Stock
from app.collectors.krx_collector import collect_krx_ohlcv, collect_stock_listing
from app.collectors.news_collector import collect_rss_news
from app.collectors.us_collector import collect_us_ohlcv
from app.core.config import settings
from app.database.session import async_session_factory
from app.service.db_service import (
    bulk_insert_daily_prices,
    get_daily_prices,
    get_recent_news,
    get_stock_by_ticker,
    get_stock_id_map,
    log_collection,
    save_analysis_report,
    upsert_news_articles,
    upsert_stocks,
)
from app.utils.alerting import notify_failure
from app.utils.market_calendar import is_krx_trading_day, is_nyse_trading_day

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


async def job_pre_market() -> None:
    """장 시작 전 종목 리스팅 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="pre_market", started_at=started_at.isoformat())
    try:
        df = await collect_stock_listing()
        async with async_session_factory() as session:
            count = await upsert_stocks(session, df)
            completed_at = datetime.now(tz=KST)
            await log_collection(
                session,
                job_type="pre_market",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=started_at.date(),
                stocks_count=count,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="pre_market",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            stocks_count=count,
        )
    except Exception as exc:
        logger.exception("job_failed", job="pre_market")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="pre_market",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("pre_market", exc, started_at)


async def job_krx_close() -> None:
    """KRX 장 마감 후 OHLCV 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="krx_close", started_at=started_at.isoformat())
    try:
        if not is_krx_trading_day():
            logger.info("job_skipped", job="krx_close", reason="not_trading_day")
            return
        today = date.today()
        data = await collect_krx_ohlcv()
        data["date"] = today
        async with async_session_factory() as session:
            stock_id_map = await get_stock_id_map(session)
            count = await bulk_insert_daily_prices(session, data, stock_id_map, market="KRX")
            completed_at = datetime.now(tz=KST)
            await log_collection(
                session,
                job_type="krx_close",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=today,
                stocks_count=count,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="krx_close",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            stocks_count=count,
        )
    except Exception as exc:
        logger.exception("job_failed", job="krx_close")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="krx_close",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("krx_close", exc, started_at)


async def job_news_collect() -> None:
    """RSS 뉴스 수집 + 종목 매칭."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="news_collect", started_at=started_at.isoformat())
    try:
        articles = await collect_rss_news()
        async with async_session_factory() as session:
            stock_id_map = await get_stock_id_map(session)
            result = await session.execute(select(Stock.name, Stock.id))
            name_map = {row.name: row.id for row in result}
            full_map = {**stock_id_map, **name_map}
            count = await upsert_news_articles(session, articles, stock_id_map=full_map)
            completed_at = datetime.now(tz=KST)
            await log_collection(
                session,
                job_type="news_collect",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=started_at.date(),
                stocks_count=count,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="news_collect",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            article_count=count,
        )
    except Exception as exc:
        logger.exception("job_failed", job="news_collect")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="news_collect",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("news_collect", exc, started_at)


async def _get_market_context() -> str:
    """pykrx로 KOSPI/KOSDAQ 당일 종가 및 등락률을 조회한다."""
    from pykrx import stock as pykrx_stock

    today_str = datetime.now(tz=KST).date().strftime("%Y%m%d")
    try:
        kospi_df = await asyncio.to_thread(
            pykrx_stock.get_index_ohlcv_by_date, today_str, today_str, "1001",
        )
        kosdaq_df = await asyncio.to_thread(
            pykrx_stock.get_index_ohlcv_by_date, today_str, today_str, "2001",
        )

        parts = []
        if not kospi_df.empty:
            row = kospi_df.iloc[-1]
            kospi_close = row["종가"]
            kospi_change = row["등락률"]
            parts.append(f"KOSPI: {kospi_close:,.2f} ({kospi_change:+.2f}%)")
        else:
            parts.append("KOSPI: 데이터 없음")

        if not kosdaq_df.empty:
            row = kosdaq_df.iloc[-1]
            kosdaq_close = row["종가"]
            kosdaq_change = row["등락률"]
            parts.append(f"KOSDAQ: {kosdaq_close:,.2f} ({kosdaq_change:+.2f}%)")
        else:
            parts.append("KOSDAQ: 데이터 없음")

        return "\n".join(parts)
    except Exception:
        logger.warning("market_context_fetch_failed", exc_info=True)
        return "시장 지수 데이터 조회 실패"


async def job_claude_analysis() -> None:
    """Claude 기반 시장 분석."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="claude_analysis", started_at=started_at.isoformat())
    try:
        if not is_krx_trading_day():
            logger.info("job_skipped", job="claude_analysis", reason="not_trading_day")
            return

        runner = ClaudeRunner(
            claude_path=settings.CLAUDE_PATH,
            timeout=settings.CLAUDE_TIMEOUT,
        )
        semaphore = asyncio.Semaphore(2)
        today = date.today()

        market_context = await _get_market_context()

        async def _analyze_ticker(ticker: str) -> None:
            async with semaphore:
                async with async_session_factory() as session:
                    stock = await get_stock_by_ticker(session, ticker)
                    if not stock:
                        logger.warning("stock_not_found", ticker=ticker)
                        return

                    prices = await get_daily_prices(session, stock.id, limit=5)
                    news = await get_recent_news(session, stock.id, limit=5)

                    prices_df = pd.DataFrame([
                        {
                            "date": p.trade_date,
                            "close": float(p.close),
                            "change_pct": 0.0,
                            "volume": p.volume,
                        }
                        for p in prices
                    ])
                    news_list = [
                        {"title": n.title, "sentiment": n.sentiment_label or ""}
                        for n in news
                    ]

                    analysis_result = await run_stock_analysis(
                        runner=runner,
                        ticker=ticker,
                        name=stock.name,
                        prices_df=prices_df,
                        news_list=news_list,
                        market_ctx=market_context,
                    )

                    await save_analysis_report(
                        session,
                        stock_id=stock.id,
                        analysis_date=today,
                        analysis_type="daily",
                        result=analysis_result.model_dump(),
                        model_used="claude-code-headless",
                    )
                    await session.commit()
                    logger.info("claude_analysis_done", ticker=ticker)

        tasks = [_analyze_ticker(t) for t in settings.KR_WATCHLIST]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        fail_count = 0
        for r in results:
            if isinstance(r, Exception):
                fail_count += 1
                logger.warning("analysis_ticker_failed", error=str(r))
            else:
                success_count += 1

        status = "failure" if success_count == 0 and fail_count > 0 else "success"

        async with async_session_factory() as session:
            completed_at = datetime.now(tz=KST)
            await log_collection(
                session,
                job_type="claude_analysis",
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                target_date=today,
                stocks_count=success_count,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="claude_analysis",
            status=status,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            success_count=success_count,
            fail_count=fail_count,
        )
    except Exception as exc:
        logger.exception("job_failed", job="claude_analysis")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="claude_analysis",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("claude_analysis", exc, started_at)


async def job_us_close() -> None:
    """미국 장 마감 후 OHLCV 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="us_close", started_at=started_at.isoformat())
    try:
        if not is_nyse_trading_day():
            logger.info("job_skipped", job="us_close", reason="not_trading_day")
            return
        today = date.today()
        data = await collect_us_ohlcv(settings.US_WATCHLIST)
        data["date"] = today
        async with async_session_factory() as session:
            stock_id_map = await get_stock_id_map(session)
            count = await bulk_insert_daily_prices(session, data, stock_id_map, market="US")
            completed_at = datetime.now(tz=KST)
            await log_collection(
                session,
                job_type="us_close",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=today,
                stocks_count=count,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="us_close",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            stocks_count=count,
        )
    except Exception as exc:
        logger.exception("job_failed", job="us_close")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="us_close",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("us_close", exc, started_at)
