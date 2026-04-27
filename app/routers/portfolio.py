"""포트폴리오 API 라우터."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.service import db_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
TWOPLACES = Decimal("0.01")


class PortfolioHoldingCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    average_price: Decimal = Field(gt=0)


class PortfolioHoldingUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str | None = Field(default=None, min_length=1)
    quantity: Decimal | None = Field(default=None, gt=0)
    average_price: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_any_field_present(self) -> PortfolioHoldingUpdateRequest:
        if self.ticker is None and self.quantity is None and self.average_price is None:
            raise ValueError("최소 한 개 이상의 수정 필드가 필요합니다")
        return self


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


async def _resolve_stock_or_404(session: AsyncSession, ticker: str):
    normalized = _normalize_ticker(ticker)
    stock = await db_service.get_stock_by_ticker(session, normalized)
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목을 찾을 수 없습니다: {normalized}",
        )
    return stock


async def _serialize_holding(
    session: AsyncSession,
    holding,
    allocation_percent: Decimal | None = None,
) -> dict[str, Any]:
    latest_price_row = await db_service.get_latest_daily_price(session, holding.stock_id)
    invested_amount = _quantize_money(holding.quantity * holding.average_price)
    is_price_missing = latest_price_row is None
    latest_price = latest_price_row.close if latest_price_row else None
    latest_valuation = None
    unrealized_pnl = None
    unrealized_pnl_percent = None
    latest_trade_date = None

    if latest_price_row is not None:
        latest_trade_date = str(latest_price_row.trade_date)
        latest_valuation = _quantize_money(holding.quantity * latest_price_row.close)
        unrealized_pnl = _quantize_money(latest_valuation - invested_amount)
        if invested_amount > 0:
            unrealized_pnl_percent = _quantize_money(
                (unrealized_pnl / invested_amount) * Decimal("100")
            )

    return {
        "id": holding.id,
        "ticker": holding.stock.ticker,
        "name": holding.stock.name,
        "market": holding.market,
        "currency": holding.currency,
        "quantity": _decimal_to_float(holding.quantity),
        "average_price": _decimal_to_float(holding.average_price),
        "invested_amount": _decimal_to_float(invested_amount),
        "latest_trade_date": latest_trade_date,
        "latest_price": _decimal_to_float(latest_price),
        "latest_valuation": _decimal_to_float(latest_valuation),
        "unrealized_pnl": _decimal_to_float(unrealized_pnl),
        "unrealized_pnl_percent": _decimal_to_float(unrealized_pnl_percent),
        "allocation_percent": _decimal_to_float(allocation_percent),
        "is_price_missing": is_price_missing,
        "created_at": str(holding.created_at) if holding.created_at else None,
        "updated_at": str(holding.updated_at) if holding.updated_at else None,
    }


async def _serialize_holdings_with_allocation(
    session: AsyncSession,
    holdings: list,
) -> list[dict[str, Any]]:
    serialized = [await _serialize_holding(session, holding) for holding in holdings]
    has_missing_prices = any(item["is_price_missing"] for item in serialized)
    has_mixed_currencies = len({item["currency"] for item in serialized}) > 1
    if has_missing_prices or has_mixed_currencies:
        return serialized

    total_valuation = sum(
        Decimal(str(item["latest_valuation"]))
        for item in serialized
        if item["latest_valuation"] is not None
    )
    if total_valuation <= 0:
        return serialized

    for item in serialized:
        latest_valuation = item["latest_valuation"]
        if latest_valuation is None:
            continue
        allocation_percent = _quantize_money(
            (Decimal(str(latest_valuation)) / total_valuation) * Decimal("100")
        )
        item["allocation_percent"] = float(allocation_percent)

    return serialized


def _build_currency_breakdown(serialized_holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in serialized_holdings:
        grouped.setdefault(item["currency"], []).append(item)

    breakdown: list[dict[str, Any]] = []
    for currency, items in grouped.items():
        invested_amount = _quantize_money(
            sum(Decimal(str(item["invested_amount"])) for item in items)
        )
        has_missing_prices = any(item["is_price_missing"] for item in items)

        latest_valuation = None
        unrealized_pnl = None
        unrealized_pnl_percent = None

        if not has_missing_prices:
            latest_valuation = _quantize_money(
                sum(Decimal(str(item["latest_valuation"])) for item in items)
            )
            unrealized_pnl = _quantize_money(latest_valuation - invested_amount)
            if invested_amount > 0:
                unrealized_pnl_percent = _quantize_money(
                    (unrealized_pnl / invested_amount) * Decimal("100")
                )

        breakdown.append(
            {
                "currency": currency,
                "invested_amount": _decimal_to_float(invested_amount),
                "latest_valuation": _decimal_to_float(latest_valuation),
                "unrealized_pnl": _decimal_to_float(unrealized_pnl),
                "unrealized_pnl_percent": _decimal_to_float(unrealized_pnl_percent),
                "has_missing_prices": has_missing_prices,
            }
        )

    return breakdown


def _sum_decimal(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0"))


@router.post("/holdings", status_code=status.HTTP_201_CREATED)
async def create_portfolio_holding(
    payload: PortfolioHoldingCreateRequest,
    session: DbSession,
) -> dict[str, Any]:
    stock = await _resolve_stock_or_404(session, payload.ticker)
    existing = await db_service.get_portfolio_holding_by_stock_id(session, stock.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 보유 중인 종목입니다: {stock.ticker}",
        )

    holding = await db_service.create_portfolio_holding(
        session=session,
        stock=stock,
        quantity=payload.quantity,
        average_price=payload.average_price,
    )
    await session.commit()
    return await _serialize_holding(session, holding)


@router.get("/holdings")
async def list_portfolio_holdings(session: DbSession) -> dict[str, Any]:
    holdings = await db_service.list_portfolio_holdings(session)
    serialized = await _serialize_holdings_with_allocation(session, holdings)
    return {"holdings": serialized}


@router.patch("/holdings/{holding_id}")
async def update_portfolio_holding(
    holding_id: int,
    payload: PortfolioHoldingUpdateRequest,
    session: DbSession,
) -> dict[str, Any]:
    holding = await db_service.get_portfolio_holding(session, holding_id)
    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"보유 종목을 찾을 수 없습니다: {holding_id}",
        )

    next_ticker = payload.ticker or holding.stock.ticker
    stock = await _resolve_stock_or_404(session, next_ticker)
    if stock.id != holding.stock_id:
        duplicate = await db_service.get_portfolio_holding_by_stock_id(session, stock.id)
        if duplicate and duplicate.id != holding.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"이미 보유 중인 종목입니다: {stock.ticker}",
            )

    updated = await db_service.update_portfolio_holding(
        session=session,
        holding=holding,
        stock=stock,
        quantity=payload.quantity if payload.quantity is not None else holding.quantity,
        average_price=(
            payload.average_price if payload.average_price is not None else holding.average_price
        ),
    )
    await session.commit()
    return await _serialize_holding(session, updated)


@router.delete("/holdings/{holding_id}")
async def delete_portfolio_holding(holding_id: int, session: DbSession) -> dict[str, Any]:
    holding = await db_service.get_portfolio_holding(session, holding_id)
    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"보유 종목을 찾을 수 없습니다: {holding_id}",
        )

    await db_service.delete_portfolio_holding(session, holding)
    await session.commit()
    return {"deleted": True, "holding_id": holding_id}


@router.get("/summary")
async def get_portfolio_summary(session: DbSession) -> dict[str, Any]:
    holdings = await db_service.list_portfolio_holdings(session)
    serialized_holdings = await _serialize_holdings_with_allocation(session, holdings)
    if not serialized_holdings:
        return {
            "invested_amount": 0.0,
            "latest_valuation": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": None,
            "has_missing_prices": False,
            "has_mixed_currencies": False,
            "currency_breakdown": [],
            "holdings": [],
            "allocation": [],
        }

    has_missing_prices = any(item["is_price_missing"] for item in serialized_holdings)
    has_mixed_currencies = len({item["currency"] for item in serialized_holdings}) > 1
    currency_breakdown = _build_currency_breakdown(serialized_holdings)

    invested_amount = None
    if not has_mixed_currencies:
        invested_amount = _quantize_money(
            _sum_decimal(
                [Decimal(str(item["invested_amount"])) for item in serialized_holdings]
            )
        )

    latest_valuation = None
    unrealized_pnl = None
    unrealized_pnl_percent = None

    if not has_missing_prices and not has_mixed_currencies and invested_amount is not None:
        latest_valuation = _quantize_money(
            _sum_decimal(
                [Decimal(str(item["latest_valuation"])) for item in serialized_holdings]
            )
        )
        unrealized_pnl = _quantize_money(latest_valuation - invested_amount)
        if invested_amount > 0:
            unrealized_pnl_percent = _quantize_money(
                (unrealized_pnl / invested_amount) * Decimal("100")
            )

    allocation = [
        {
            "holding_id": item["id"],
            "ticker": item["ticker"],
            "name": item["name"],
            "market": item["market"],
            "currency": item["currency"],
            "latest_valuation": item["latest_valuation"],
            "allocation_percent": item["allocation_percent"],
            "is_price_missing": item["is_price_missing"],
        }
        for item in serialized_holdings
    ]

    return {
        "invested_amount": _decimal_to_float(invested_amount),
        "latest_valuation": _decimal_to_float(latest_valuation),
        "unrealized_pnl": _decimal_to_float(unrealized_pnl),
        "unrealized_pnl_percent": _decimal_to_float(unrealized_pnl_percent),
        "has_missing_prices": has_missing_prices,
        "has_mixed_currencies": has_mixed_currencies,
        "currency_breakdown": currency_breakdown,
        "holdings": serialized_holdings,
        "allocation": allocation,
    }
