"""헬스체크 라우터."""

from typing import Any

import structlog
from fastapi import APIRouter

from app.scheduler.scheduler import get_scheduler

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """애플리케이션 헬스 상태 및 스케줄러 잡 목록을 반환한다."""
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )

    return {
        "status": "ok",
        "jobs": jobs,
        # TODO: collection_logs 테이블에서 마지막 수집 시각 조회
        "last_collection": None,
    }
