"""개인용 알림 규칙 API 라우터."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.service.alerts_service import (
    create_alert_rule,
    delete_alert_rule,
    evaluate_alert_rules,
    list_alert_events,
    list_alert_rules,
    update_alert_rule,
)
from app.service.db_service import get_stock_by_ticker

router = APIRouter(prefix="/alerts", tags=["alerts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
RuleType = Literal["target_price", "rsi_threshold", "sentiment_change", "recommendation_change"]


class AlertRulePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    rule_type: RuleType
    direction: str | None = None
    threshold_value: Decimal | None = Field(default=None, gt=0)
    target_recommendation: str | None = None
    lookback_days: int = Field(default=2, ge=1, le=30)


class AlertRuleUpdatePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    direction: str | None = None
    threshold_value: Decimal | None = Field(default=None, gt=0)
    target_recommendation: str | None = None
    lookback_days: int | None = Field(default=None, ge=1, le=30)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_any_field_present(self) -> AlertRuleUpdatePayload:
        if all(
            value is None
            for value in (
                self.name,
                self.direction,
                self.threshold_value,
                self.target_recommendation,
                self.lookback_days,
                self.is_active,
            )
        ):
            raise ValueError("최소 한 개 이상의 수정 필드가 필요합니다")
        return self


class AlertRuleResponse(BaseModel):
    id: int
    ticker: str | None
    name: str
    rule_type: str
    direction: str | None
    threshold_value: float | None
    target_recommendation: str | None
    lookback_days: int
    is_active: bool
    last_evaluated_at: str | None
    last_triggered_at: str | None


class AlertEventResponse(BaseModel):
    id: int
    rule_id: int
    ticker: str | None
    rule_type: str
    status: str
    observed_value: float | None
    observed_text: str | None
    baseline_value: float | None
    baseline_text: str | None
    threshold_value: float | None
    threshold_text: str | None
    observed_at: str | None
    message: str
    created_at: str | None


class AlertEvaluationSummary(BaseModel):
    rule_id: int
    ticker: str
    rule_type: str
    status: str
    observed_value: float | None
    observed_text: str | None
    baseline_value: float | None
    baseline_text: str | None
    threshold_value: float | None
    threshold_text: str | None
    observed_at: str | None
    message: str


class AlertEvaluationResponse(BaseModel):
    evaluated_count: int
    triggered_count: int
    triggered_events: list[AlertEventResponse]
    pending_rules: list[AlertEvaluationSummary]


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules_endpoint(session: DbSession) -> list[dict[str, Any]]:
    """개인용 알림 규칙 목록을 반환한다."""
    return await list_alert_rules(session)


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule_endpoint(
    payload: AlertRulePayload,
    session: DbSession,
) -> dict[str, Any]:
    """개인용 알림 규칙을 생성한다."""
    stock = await get_stock_by_ticker(session, payload.ticker.upper())
    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {payload.ticker.upper()}",
        )

    try:
        result = await create_alert_rule(
            session,
            stock=stock,
            rule_type=payload.rule_type,
            name=payload.name,
            direction=payload.direction,
            threshold_value=payload.threshold_value,
            target_recommendation=payload.target_recommendation,
            lookback_days=payload.lookback_days,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule_endpoint(
    rule_id: int,
    payload: AlertRuleUpdatePayload,
    session: DbSession,
) -> dict[str, Any]:
    """개인용 알림 규칙을 수정한다."""
    try:
        result = await update_alert_rule(
            session,
            rule_id=rule_id,
            name=payload.name,
            direction=payload.direction,
            threshold_value=payload.threshold_value,
            target_recommendation=payload.target_recommendation,
            lookback_days=payload.lookback_days,
            is_active=payload.is_active,
        )
        await session.commit()
        return result
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete("/rules/{rule_id}")
async def delete_alert_rule_endpoint(rule_id: int, session: DbSession) -> dict[str, Any]:
    """개인용 알림 규칙을 삭제한다."""
    try:
        result = await delete_alert_rule(session, rule_id=rule_id)
        await session.commit()
        return result
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/events", response_model=list[AlertEventResponse])
async def list_alert_events_endpoint(
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """최근 알림 이벤트를 반환한다."""
    return await list_alert_events(session, limit=limit)


@router.post("/evaluate", response_model=AlertEvaluationResponse)
async def evaluate_alert_rules_endpoint(session: DbSession) -> dict[str, Any]:
    """활성화된 개인용 알림 규칙을 즉시 평가한다."""
    result = await evaluate_alert_rules(session)
    await session.commit()
    return result
