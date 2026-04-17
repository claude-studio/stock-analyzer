"""FastAPI 앱 엔트리포인트."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.routers import health, stocks
from app.scheduler.scheduler import get_scheduler, register_jobs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 시작/종료 시 스케줄러 및 로깅을 관리한다."""
    setup_logging()
    scheduler = get_scheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info("application_started", mode=settings.MODE)
    yield
    scheduler.shutdown(wait=False)
    logger.info("application_stopped")


docs_url: str | None = "/docs" if settings.MODE != "PRD" else None
redoc_url: str | None = "/redoc" if settings.MODE != "PRD" else None

app = FastAPI(
    title="Stock Analyzer",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://stock.brian-dev.cloud",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(stocks.router)
