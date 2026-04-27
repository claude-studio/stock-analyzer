"""개인용 백테스트 API 라우터."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.service.backtest_service import run_backtest

router = APIRouter(prefix="/backtests", tags=["backtests"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str = Field(min_length=1)
    strategy: Literal["daily_recommendation_follow"]
    start_date: date
    end_date: date
    initial_capital: Decimal = Field(default=Decimal("100000.00"), gt=0)


class BacktestSummary(BaseModel):
    start_date: str
    end_date: str
    initial_capital: float
    ending_capital: float
    total_return_percent: float
    completed_trades: int
    wins: int
    losses: int
    open_position: bool
    event_count: int


class BacktestTimelineEvent(BaseModel):
    trade_date: str
    event_type: str
    price: float
    recommendation: str | None
    shares: float
    cash_balance: float
    position_value: float
    realized_return_percent: float | None = None
    message: str


class BacktestRunResponse(BaseModel):
    ticker: str
    name: str
    strategy: str
    generated_at: str
    assumptions: list[str]
    limitations: list[str]
    summary: BacktestSummary
    timeline: list[BacktestTimelineEvent]


@router.post("/run", response_model=BacktestRunResponse)
async def run_backtest_endpoint(
    payload: BacktestRunRequest,
    session: DbSession,
) -> dict[str, Any]:
    """저장된 일일 리포트/가격 기준 단순 백테스트를 실행한다."""
    try:
        return await run_backtest(
            session,
            ticker=payload.ticker.upper(),
            strategy=payload.strategy,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_capital=payload.initial_capital,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
