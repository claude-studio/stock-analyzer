"""스케줄러 잡 함수 모듈."""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import select, update

from app.analysis.analyzer import run_stock_analysis
from app.analysis.accuracy import evaluate_past_analyses
from app.analysis.claude_runner import ClaudeRunner
from app.analysis.sentiment import analyze_sentiment_batch, update_news_sentiment
from app.analysis.technical import calculate_technical_indicators
from app.collectors.dart_collector import collect_today_disclosures, collect_fundamentals_for_watchlist
from app.collectors.krx_collector import collect_krx_ohlcv, collect_investor_trading, collect_stock_listing
from app.collectors.news_collector import collect_rss_news
from app.collectors.us_collector import collect_us_ohlcv
from app.core.config import settings
from app.database.models import DailyPrice, NewsArticle, Stock
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
from app.utils.alerting import notify_failure, notify_success
from app.utils.market_calendar import is_krx_trading_day, is_nyse_trading_day
from app.utils.telegram import send_analysis_alert, send_market_summary

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")
DISCLAIMER = "이 분석은 정보 제공 목적이며 투자 권유가 아닙니다. 투자 의사결정의 최종 책임은 사용자에게 있습니다."


def _format_tech_for_prompt(indicators: dict) -> str:
    """기술적 지표 dict를 시장 컨텍스트에 합칠 텍스트로 변환한다."""
    lines: list[str] = []

    # RSI
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            interp = "과매도"
        elif rsi > 70:
            interp = "과매수"
        else:
            interp = "중립"
        lines.append(f"- RSI: {rsi:.2f} ({interp})")

    # MACD
    macd_val = indicators.get("macd")
    macd_sig = indicators.get("macd_signal")
    if macd_val is not None and macd_sig is not None:
        signal = "매수 신호" if macd_val > macd_sig else "매도 신호"
        lines.append(f"- MACD: {macd_val:,.2f}, Signal: {macd_sig:,.2f} ({signal})")

    # Bollinger Bands
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    if bb_upper is not None and bb_lower is not None:
        pos = indicators.get("price_position", "")
        lines.append(f"- 볼린저밴드: 상단={bb_upper:,.2f}, 하단={bb_lower:,.2f} ({pos})")

    # SMA
    sma_parts: list[str] = []
    for key, label in [("sma_5", "5일"), ("sma_20", "20일"), ("sma_60", "60일")]:
        val = indicators.get(key)
        if val is not None:
            sma_parts.append(f"{label}={val:,.2f}")
    if sma_parts:
        lines.append(f"- SMA: {', '.join(sma_parts)}")

    # Trend
    trend = indicators.get("trend")
    if trend:
        lines.append(f"- 추세: {trend}")

    return "\n".join(lines)


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
        today_str = today.strftime("%Y%m%d")
        data = await collect_krx_ohlcv()
        data["date"] = today
        async with async_session_factory() as session:
            stock_id_map = await get_stock_id_map(session)
            count = await bulk_insert_daily_prices(session, data, stock_id_map, market="KRX")

            # M2: 관심 종목 수급 데이터 수집
            for ticker in settings.KR_WATCHLIST:
                try:
                    inv_data = await collect_investor_trading(ticker, today_str, today_str)
                    if not inv_data.empty:
                        row = inv_data.iloc[-1]
                        inst_val = int(row.get("기관합계", 0))
                        foreign_val = int(row.get("외국인합계", 0))
                        sid = stock_id_map.get(ticker)
                        if sid:
                            stmt = (
                                update(DailyPrice)
                                .where(
                                    DailyPrice.stock_id == sid,
                                    DailyPrice.trade_date == today,
                                )
                                .values(
                                    inst_net_buy=inst_val,
                                    foreign_net_buy=foreign_val,
                                )
                            )
                            await session.execute(stmt)
                            logger.info("investor_trading_updated", ticker=ticker)
                except Exception:
                    logger.warning("investor_trading_failed", ticker=ticker, exc_info=True)

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

            # M3: 감성 분석 실행
            if articles:
                try:
                    runner = ClaudeRunner(
                        claude_path=settings.CLAUDE_PATH,
                        timeout=settings.CLAUDE_TIMEOUT,
                    )
                    headlines = [a.get("title", "") for a in articles if a.get("title")]
                    sentiments = await analyze_sentiment_batch(runner, headlines)
                    if sentiments:
                        # 방금 upsert한 기사의 ID 조회 (URL 기준)
                        urls = [
                            (a.get("link") or "").strip()
                            for a in articles
                            if (a.get("link") or "").strip()
                        ]
                        if urls:
                            id_stmt = (
                                select(NewsArticle.id)
                                .where(NewsArticle.url.in_(urls))
                                .order_by(NewsArticle.id)
                            )
                            id_result = await session.execute(id_stmt)
                            article_ids = [r[0] for r in id_result]
                            if article_ids:
                                sentiment_count = await update_news_sentiment(
                                    session, article_ids, sentiments,
                                )
                                logger.info("sentiment_analysis_done", updated=sentiment_count)
                except Exception:
                    logger.warning("sentiment_analysis_failed", exc_info=True)

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

        # B4: DART 재무 데이터 수집
        fundamentals_map: dict[str, dict] = {}
        try:
            fundamentals_map = await collect_fundamentals_for_watchlist(settings.KR_WATCHLIST)
            logger.info("fundamentals_collected", count=len(fundamentals_map))
        except Exception:
            logger.warning("fundamentals_collect_failed", exc_info=True)

        async def _analyze_ticker(ticker: str) -> None:
            async with semaphore:
                async with async_session_factory() as session:
                    stock = await get_stock_by_ticker(session, ticker)
                    if not stock:
                        logger.warning("stock_not_found", ticker=ticker)
                        return

                    # M1: 60일로 확장하여 기술적 지표 계산에 충분한 데이터 확보
                    prices = await get_daily_prices(session, stock.id, limit=60)
                    news = await get_recent_news(session, stock.id, limit=5)

                    # M1: OHLCV 전부 포함
                    prices_df = pd.DataFrame([
                        {
                            "date": p.trade_date,
                            "open": float(p.open),
                            "high": float(p.high),
                            "low": float(p.low),
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

                    # M1: 기술적 지표 계산 -> market_context에 합산
                    tech_indicators: dict = {}
                    if len(prices_df) >= 20:
                        try:
                            tech_indicators = calculate_technical_indicators(prices_df)
                        except (ValueError, KeyError):
                            logger.warning("tech_indicators_failed", ticker=ticker, exc_info=True)

                    tech_text = _format_tech_for_prompt(tech_indicators) if tech_indicators else ""

                    # B4: DART 재무 지표 합산
                    fund = fundamentals_map.get(ticker, {})
                    if fund:
                        fund_text = "\n".join(f"- {k}: {v}" for k, v in fund.items() if v is not None)
                        full_context = f"{market_context}\n\n## 기술적 지표\n{tech_text}\n\n## 재무 지표\n{fund_text}"
                    elif tech_text:
                        full_context = f"{market_context}\n\n## 기술적 지표\n{tech_text}"
                    else:
                        full_context = market_context

                    analysis_result = await run_stock_analysis(
                        runner=runner,
                        ticker=ticker,
                        name=stock.name,
                        prices_df=prices_df,
                        news_list=news_list,
                        market_ctx=full_context,
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

                    # M5: buy/strong_buy 종목 Telegram 알림
                    result_dict = analysis_result.model_dump()
                    if result_dict.get("recommendation") in ("buy", "strong_buy"):
                        try:
                            await send_analysis_alert(
                                ticker=ticker,
                                name=stock.name,
                                recommendation=result_dict["recommendation"],
                                confidence=result_dict.get("confidence", 0),
                                summary=result_dict.get("summary", ""),
                                key_factors=result_dict.get("key_factors"),
                            )
                        except Exception:
                            logger.warning("telegram_alert_failed", ticker=ticker, exc_info=True)

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

        total = len(settings.KR_WATCHLIST)
        if success_count == 0 and fail_count > 0:
            status = "failure"
        elif fail_count > 0 and success_count < total * 0.5:
            status = "partial_failure"
            await notify_failure(
                "claude_analysis",
                RuntimeError(f"{fail_count}/{total} 종목 분석 실패"),
                started_at,
            )
        else:
            status = "success"

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
            disclaimer=DISCLAIMER,
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


async def job_market_summary() -> None:
    """일일 시장 요약 리포트 생성."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="market_summary", started_at=started_at.isoformat())
    try:
        from app.analysis.prompts import build_market_summary_prompt

        market_context = await _get_market_context()

        # 당일 분석 결과 요약 수집
        today = date.today()
        recommendations_summary: list[str] = []
        async with async_session_factory() as session:
            for ticker in settings.KR_WATCHLIST:
                stock = await get_stock_by_ticker(session, ticker)
                if not stock:
                    continue
                from app.database.models import AnalysisReport
                stmt = (
                    select(AnalysisReport)
                    .where(
                        AnalysisReport.stock_id == stock.id,
                        AnalysisReport.analysis_date == today,
                    )
                    .order_by(AnalysisReport.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                report = result.scalar_one_or_none()
                if report:
                    recommendations_summary.append(
                        f"- {ticker} {stock.name}: {report.recommendation} "
                        f"(확신도: {report.confidence or 0:.0%})"
                    )

            # 당일 주요 뉴스 5건
            recent_news = await get_recent_news(session, limit=5)
            news_headlines = "\n".join(
                f"- {n.title}" for n in recent_news
            ) or "주요 뉴스 없음"

        kr_data = market_context
        rec_text = "\n".join(recommendations_summary) if recommendations_summary else "분석 결과 없음"
        kr_data_full = f"{kr_data}\n\n### 관심종목 분석 결과\n{rec_text}"

        prompt = build_market_summary_prompt(
            kr_data=kr_data_full,
            us_data="(미국 시장 데이터 별도 수집 필요)",
            news_headlines=news_headlines,
        )

        runner = ClaudeRunner(
            claude_path=settings.CLAUDE_PATH,
            timeout=settings.CLAUDE_TIMEOUT,
        )
        summary_text = await runner.run(prompt, output_format="text")
        if isinstance(summary_text, dict):
            summary_text = str(summary_text)

        # Telegram 전송
        await send_market_summary(str(summary_text))

        # Teams 알림
        await notify_success("market_summary", "일일 시장 요약 전송 완료")

        completed_at = datetime.now(tz=KST)
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="market_summary",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=today,
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="market_summary",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
        )
    except Exception as exc:
        logger.exception("job_failed", job="market_summary")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="market_summary",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("market_summary", exc, started_at)


async def job_evaluate_accuracy() -> None:
    """과거 분석 적중률 평가."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="evaluate_accuracy", started_at=started_at.isoformat())
    try:
        async with async_session_factory() as session:
            result_7d = await evaluate_past_analyses(session, lookback_days=7)
            result_30d = await evaluate_past_analyses(session, lookback_days=30)
            await session.commit()

        completed_at = datetime.now(tz=KST)
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="evaluate_accuracy",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=date.today(),
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="evaluate_accuracy",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            result_7d=result_7d,
            result_30d=result_30d,
        )
    except Exception as exc:
        logger.exception("job_failed", job="evaluate_accuracy")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="evaluate_accuracy",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("evaluate_accuracy", exc, started_at)


async def job_dart_collect() -> None:
    """DART 전자공시 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="dart_collect", started_at=started_at.isoformat())
    try:
        disclosures = await collect_today_disclosures()
        logger.info("dart_disclosures_result", count=len(disclosures))

        fundamentals = await collect_fundamentals_for_watchlist(settings.KR_WATCHLIST)
        logger.info("dart_fundamentals_result", count=len(fundamentals))

        completed_at = datetime.now(tz=KST)
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="dart_collect",
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                target_date=date.today(),
                stocks_count=len(fundamentals),
            )
            await session.commit()
        logger.info(
            "job_completed",
            job="dart_collect",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            disclosures=len(disclosures),
            fundamentals=len(fundamentals),
        )
    except Exception as exc:
        logger.exception("job_failed", job="dart_collect")
        async with async_session_factory() as session:
            await log_collection(
                session,
                job_type="dart_collect",
                status="failure",
                started_at=started_at,
                completed_at=datetime.now(tz=KST),
                error_message=str(exc),
            )
            await session.commit()
        await notify_failure("dart_collect", exc, started_at)
