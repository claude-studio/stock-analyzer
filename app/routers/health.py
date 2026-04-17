"""헬스체크 라우터."""

from typing import Any

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.analysis.claude_runner import ClaudeRunner
from app.database.session import async_session_factory
from app.scheduler.scheduler import get_scheduler

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """애플리케이션 헬스 상태 및 스케줄러 잡 목록을 반환한다."""
    checks: dict[str, str] = {}
    overall = "ok"

    # DB ping
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {str(exc)[:100]}"
        overall = "degraded"

    # Claude CLI
    try:
        runner = ClaudeRunner()
        claude_ok = await runner.health_check()
        checks["claude"] = "ok" if claude_ok else "unavailable"
        if not claude_ok:
            overall = "degraded"
    except Exception:
        checks["claude"] = "unavailable"
        overall = "degraded"

    # 스케줄러 잡 목록
    scheduler = get_scheduler()
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]

    return {
        "status": overall,
        "checks": checks,
        "jobs": jobs,
    }
