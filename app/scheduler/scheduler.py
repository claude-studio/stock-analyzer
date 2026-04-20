"""APScheduler AsyncIOScheduler 설정 모듈."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import structlog

from app.scheduler.jobs import (
    job_claude_analysis,
    job_dart_collect,
    job_evaluate_accuracy,
    job_krx_close,
    job_market_summary,
    job_news_collect,
    job_pre_market,
    job_us_close,
    job_weekly_reflection,
)

logger = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """AsyncIOScheduler 싱글톤을 반환한다."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone="Asia/Seoul",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )
        logger.info("scheduler_created")
    return _scheduler


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """스케줄러에 크론 잡을 등록한다."""
    scheduler.add_job(
        job_pre_market,
        "cron",
        id="pre_market",
        day_of_week="mon-fri",
        hour=8,
        minute=30,
        replace_existing=True,
    )
    scheduler.add_job(
        job_krx_close,
        "cron",
        id="krx_close",
        day_of_week="mon-fri",
        hour=15,
        minute=35,
        replace_existing=True,
    )
    scheduler.add_job(
        job_news_collect,
        "cron",
        id="news_collect",
        day_of_week="mon-fri",
        hour="8,12,16",
        replace_existing=True,
    )
    scheduler.add_job(
        job_claude_analysis,
        "cron",
        id="claude_analysis",
        day_of_week="mon-fri",
        hour=16,
        minute=30,
        replace_existing=True,
    )
    scheduler.add_job(
        job_us_close,
        "cron",
        id="us_close",
        day_of_week="tue-sat",
        hour=5,
        minute=30,
        replace_existing=True,
    )
    scheduler.add_job(
        job_market_summary,
        "cron",
        id="market_summary",
        day_of_week="mon-fri",
        hour=17,
        minute=0,
        replace_existing=True,
    )
    scheduler.add_job(
        job_evaluate_accuracy,
        "cron",
        id="evaluate_accuracy",
        hour=7,
        minute=0,
        replace_existing=True,
    )
    scheduler.add_job(
        job_dart_collect,
        "cron",
        id="dart_collect",
        day_of_week="mon-fri",
        hour=16,
        minute=10,
        replace_existing=True,
    )
    scheduler.add_job(
        job_weekly_reflection,
        "cron",
        id="weekly_reflection",
        day_of_week="fri",
        hour=18,
        minute=0,
        replace_existing=True,
    )
    logger.info("scheduler_jobs_registered", job_count=len(scheduler.get_jobs()))
