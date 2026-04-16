"""스케줄러 잡 함수 모듈."""

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog

from app.collectors.krx_collector import collect_krx_ohlcv, collect_stock_listing
from app.collectors.news_collector import collect_rss_news
from app.collectors.us_collector import collect_us_ohlcv
from app.utils.alerting import notify_failure
from app.utils.market_calendar import is_krx_trading_day, is_nyse_trading_day

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


async def job_pre_market() -> None:
    """장 시작 전 종목 리스팅 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="pre_market", started_at=started_at.isoformat())
    try:
        await collect_stock_listing()
        completed_at = datetime.now(tz=KST)
        logger.info(
            "job_completed",
            job="pre_market",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
        )
    except Exception as exc:
        logger.exception("job_failed", job="pre_market")
        await notify_failure("pre_market", exc, started_at)


async def job_krx_close() -> None:
    """KRX 장 마감 후 OHLCV 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="krx_close", started_at=started_at.isoformat())
    try:
        if not is_krx_trading_day():
            logger.info("job_skipped", job="krx_close", reason="not_trading_day")
            return
        data = await collect_krx_ohlcv()
        # TODO: DB 저장 - collected data를 stocks_ohlcv 테이블에 bulk insert
        completed_at = datetime.now(tz=KST)
        logger.info(
            "job_completed",
            job="krx_close",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
        )
    except Exception as exc:
        logger.exception("job_failed", job="krx_close")
        await notify_failure("krx_close", exc, started_at)


async def job_news_collect() -> None:
    """RSS 뉴스 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="news_collect", started_at=started_at.isoformat())
    try:
        articles = await collect_rss_news()
        # TODO: DB 저장 - articles를 news 테이블에 upsert (link 기준 중복 제거)
        completed_at = datetime.now(tz=KST)
        logger.info(
            "job_completed",
            job="news_collect",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
            article_count=len(articles) if articles else 0,
        )
    except Exception as exc:
        logger.exception("job_failed", job="news_collect")
        await notify_failure("news_collect", exc, started_at)


async def job_claude_analysis() -> None:
    """Claude 기반 시장 분석."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="claude_analysis", started_at=started_at.isoformat())
    try:
        if not is_krx_trading_day():
            logger.info("job_skipped", job="claude_analysis", reason="not_trading_day")
            return
        # TODO: DB에서 당일 OHLCV/뉴스 데이터 조회 후 Claude 분석 실행
        # 1. stocks_ohlcv에서 당일 데이터 조회
        # 2. news에서 당일 뉴스 조회
        # 3. Claude CLI로 분석 프롬프트 실행
        # 4. 분석 결과를 analysis_reports 테이블에 저장
        completed_at = datetime.now(tz=KST)
        logger.info(
            "job_completed",
            job="claude_analysis",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
        )
    except Exception as exc:
        logger.exception("job_failed", job="claude_analysis")
        await notify_failure("claude_analysis", exc, started_at)


async def job_us_close() -> None:
    """미국 장 마감 후 OHLCV 수집."""
    started_at = datetime.now(tz=KST)
    logger.info("job_started", job="us_close", started_at=started_at.isoformat())
    try:
        if not is_nyse_trading_day():
            logger.info("job_skipped", job="us_close", reason="not_trading_day")
            return
        data = await collect_us_ohlcv()
        # TODO: DB 저장 - collected data를 us_stocks_ohlcv 테이블에 bulk insert
        completed_at = datetime.now(tz=KST)
        logger.info(
            "job_completed",
            job="us_close",
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            elapsed_seconds=(completed_at - started_at).total_seconds(),
        )
    except Exception as exc:
        logger.exception("job_failed", job="us_close")
        await notify_failure("us_close", exc, started_at)
