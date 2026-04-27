"""개인용 종목 스크리너 API 라우터."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.service.db_service import get_personal_screener as get_personal_screener_payload

router = APIRouter(prefix="/screener", tags=["screener"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ScreenerCoverage(BaseModel):
    ranked_markets: list[str]
    excluded_markets: list[str]
    uses_stored_data_only: bool
    eligible_stocks: int
    insufficient_stocks: int


class ScreenerEmptyState(BaseModel):
    title: str
    description: str


class ScreenerComponents(BaseModel):
    price_momentum_pct: float | None
    price_momentum_score: float | None
    volume_spike_ratio: float | None
    volume_spike_score: float | None
    recent_news_count: int
    recent_news_score: float | None
    avg_news_impact_score: float | None
    news_impact_score: float | None
    latest_daily_recommendation: str | None
    latest_daily_recommendation_score: float | None


class ScreenerCandidate(BaseModel):
    ticker: str
    name: str
    market: str
    sector: str | None
    score: float
    components: ScreenerComponents
    reasons: list[str]
    latest_recommendation: str | None
    analysis_date: str | None
    latest_close: float | None
    latest_trade_date: str | None


class ScreenerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[ScreenerCandidate]
    total_candidates: int
    total_eligible: int
    total_insufficient: int
    limit: int
    lookback_days: int
    news_window_days: int
    minimum_price_points: int
    reference_trade_date: str | None
    generated_at: str
    coverage: ScreenerCoverage
    limitations: list[str]
    empty_state: ScreenerEmptyState


@router.get("", response_model=ScreenerResponse)
async def get_personal_screener(
    session: DbSession,
    limit: int = Query(default=10, ge=1, le=30),
    lookback_days: int = Query(default=30, ge=7, le=90),
) -> dict:
    """저장된 KRX 데이터 기준 아이디어 탐색용 개인 스크리너를 반환한다."""
    return await get_personal_screener_payload(
        session,
        limit=limit,
        lookback_days=lookback_days,
    )
