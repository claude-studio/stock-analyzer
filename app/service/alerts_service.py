"""개인용 알림 규칙/이벤트 서비스."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    AlertEvent,
    AlertRule,
    AnalysisReport,
    DailyPrice,
    NewsArticle,
    Stock,
)

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")
SUPPORTED_RULE_TYPES = {
    "target_price",
    "rsi_threshold",
    "sentiment_change",
    "recommendation_change",
}


def _as_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _serialize_rule(rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "ticker": rule.stock.ticker if rule.stock else None,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "direction": rule.direction,
        "threshold_value": _as_float(rule.threshold_value),
        "target_recommendation": rule.target_recommendation,
        "lookback_days": rule.lookback_days,
        "is_active": rule.is_active,
        "last_evaluated_at": (
            rule.last_evaluated_at.isoformat() if rule.last_evaluated_at else None
        ),
        "last_triggered_at": (
            rule.last_triggered_at.isoformat() if rule.last_triggered_at else None
        ),
    }


def _serialize_event(event: AlertEvent) -> dict:
    return {
        "id": event.id,
        "rule_id": event.rule_id,
        "ticker": event.stock.ticker if event.stock else None,
        "rule_type": event.rule_type,
        "status": event.status,
        "observed_value": _as_float(event.observed_value),
        "observed_text": event.observed_text,
        "baseline_value": _as_float(event.baseline_value),
        "baseline_text": event.baseline_text,
        "threshold_value": _as_float(event.threshold_value),
        "threshold_text": event.threshold_text,
        "observed_at": event.observed_at.date().isoformat() if event.observed_at else None,
        "message": event.message,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _calculate_latest_rsi(closes: list[Decimal], period: int = 14) -> Decimal | None:
    if len(closes) < period + 1:
        return None

    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(delta if delta > 0 else Decimal("0"))
        losses.append(-delta if delta < 0 else Decimal("0"))

    recent_gains = gains[-period:]
    recent_losses = losses[-period:]
    average_gain = sum(recent_gains, Decimal("0")) / Decimal(period)
    average_loss = sum(recent_losses, Decimal("0")) / Decimal(period)
    if average_loss == 0:
        return Decimal("100")
    rs = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def _compose_observed_at_from_date(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=KST)
    if isinstance(value, str):
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=KST)
    return datetime.combine(value, time.min, tzinfo=KST)


def _build_dedupe_key(summary: dict) -> str:
    return "|".join(
        [
            str(summary["rule_id"]),
            summary.get("observed_at") or "-",
            str(summary.get("observed_value")),
            summary.get("observed_text") or "-",
            str(summary.get("baseline_value")),
            summary.get("baseline_text") or "-",
            str(summary.get("threshold_value")),
            summary.get("threshold_text") or "-",
        ]
    )


def _validate_rule_payload(
    *,
    rule_type: str,
    direction: str | None,
    threshold_value: Decimal | None,
    target_recommendation: str | None,
) -> None:
    if rule_type not in SUPPORTED_RULE_TYPES:
        raise ValueError(f"지원하지 않는 rule_type입니다: {rule_type}")

    if (
        rule_type in {"target_price", "rsi_threshold", "sentiment_change"}
        and threshold_value is None
    ):
        raise ValueError("threshold_value가 필요합니다")
    if (
        rule_type in {"target_price", "rsi_threshold"}
        and direction not in {"above", "below"}
    ):
        raise ValueError("direction은 above/below 중 하나여야 합니다")
    if rule_type == "sentiment_change" and direction not in {"up", "down"}:
        raise ValueError("sentiment_change direction은 up/down 중 하나여야 합니다")
    if rule_type == "recommendation_change" and not target_recommendation:
        raise ValueError("recommendation_change에는 target_recommendation이 필요합니다")


async def create_alert_rule(
    session: AsyncSession,
    *,
    stock: Stock,
    rule_type: str,
    name: str,
    direction: str | None = None,
    threshold_value: Decimal | None = None,
    target_recommendation: str | None = None,
    lookback_days: int | None = None,
) -> dict:
    """새 알림 규칙을 생성한다."""
    _validate_rule_payload(
        rule_type=rule_type,
        direction=direction,
        threshold_value=threshold_value,
        target_recommendation=target_recommendation,
    )
    rule = AlertRule(
        stock_id=stock.id,
        stock=stock,
        name=name,
        rule_type=rule_type,
        direction=direction,
        threshold_value=threshold_value,
        target_recommendation=_normalize_text(target_recommendation),
        lookback_days=lookback_days or 2,
        is_active=True,
    )
    session.add(rule)
    await session.flush()
    return _serialize_rule(rule)


async def list_alert_rules(session: AsyncSession) -> list[dict]:
    """알림 규칙 목록을 반환한다."""
    result = await session.execute(
        select(AlertRule)
        .options(selectinload(AlertRule.stock))
        .order_by(AlertRule.id.asc())
    )
    return [_serialize_rule(rule) for rule in result.scalars().all()]


async def update_alert_rule(
    session: AsyncSession,
    *,
    rule_id: int,
    **changes,
) -> dict:
    """알림 규칙을 수정한다."""
    result = await session.execute(
        select(AlertRule)
        .options(selectinload(AlertRule.stock))
        .where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise LookupError(f"알림 규칙을 찾을 수 없습니다: {rule_id}")

    direction = changes.get("direction", rule.direction)
    threshold_value = changes.get("threshold_value", rule.threshold_value)
    target_recommendation = changes.get(
        "target_recommendation",
        rule.target_recommendation,
    )
    _validate_rule_payload(
        rule_type=changes.get("rule_type", rule.rule_type),
        direction=direction,
        threshold_value=threshold_value,
        target_recommendation=target_recommendation,
    )

    for field in ("name", "direction", "threshold_value", "lookback_days", "is_active"):
        if field in changes and changes[field] is not None:
            setattr(rule, field, changes[field])

    if "target_recommendation" in changes:
        rule.target_recommendation = _normalize_text(changes["target_recommendation"])

    await session.flush()
    return _serialize_rule(rule)


async def delete_alert_rule(session: AsyncSession, *, rule_id: int) -> dict:
    """알림 규칙을 삭제한다."""
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise LookupError(f"알림 규칙을 찾을 수 없습니다: {rule_id}")
    await session.delete(rule)
    await session.flush()
    return {"deleted": True, "rule_id": rule_id}


async def list_alert_events(session: AsyncSession, *, limit: int = 50) -> list[dict]:
    """최근 알림 이벤트 목록을 반환한다."""
    result = await session.execute(
        select(AlertEvent)
        .options(selectinload(AlertEvent.stock))
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
        .limit(limit)
    )
    return [_serialize_event(event) for event in result.scalars().all()]


async def _evaluate_target_price_rule(session: AsyncSession, rule: AlertRule) -> dict:
    price_result = await session.execute(
        select(DailyPrice)
        .where(DailyPrice.stock_id == rule.stock_id)
        .order_by(DailyPrice.trade_date.desc())
        .limit(1)
    )
    latest_price = price_result.scalar_one_or_none()
    if latest_price is None:
        return {
            "rule_id": rule.id,
            "ticker": rule.stock.ticker,
            "rule_type": rule.rule_type,
            "status": "pending",
            "observed_value": None,
            "observed_text": None,
            "baseline_value": None,
            "baseline_text": None,
            "threshold_value": _as_float(rule.threshold_value),
            "threshold_text": None,
            "observed_at": None,
            "message": "최신 종가 데이터가 없어 아직 평가할 수 없습니다.",
            "triggered": False,
        }

    close_value = Decimal(latest_price.close)
    threshold = Decimal(rule.threshold_value or 0)
    is_triggered = (
        close_value >= threshold
        if rule.direction == "above"
        else close_value <= threshold
    )
    return {
        "rule_id": rule.id,
        "ticker": rule.stock.ticker,
        "rule_type": rule.rule_type,
        "status": "triggered" if is_triggered else "pending",
        "observed_value": round(float(close_value), 4),
        "observed_text": None,
        "baseline_value": None,
        "baseline_text": None,
        "threshold_value": round(float(threshold), 4),
        "threshold_text": None,
        "observed_at": latest_price.trade_date.isoformat(),
        "message": (
            "최신 종가가 목표가를 넘었습니다."
            if is_triggered
            else "최신 종가가 아직 목표가에 도달하지 않았습니다."
        ),
        "triggered": is_triggered,
    }


async def _evaluate_rsi_rule(session: AsyncSession, rule: AlertRule) -> dict:
    prices_result = await session.execute(
        select(DailyPrice)
        .where(DailyPrice.stock_id == rule.stock_id)
        .order_by(DailyPrice.trade_date.asc())
    )
    prices = prices_result.scalars().all()
    rsi = _calculate_latest_rsi([Decimal(price.close) for price in prices])
    latest_price = prices[-1] if prices else None
    if rsi is None or latest_price is None:
        return {
            "rule_id": rule.id,
            "ticker": rule.stock.ticker,
            "rule_type": rule.rule_type,
            "status": "pending",
            "observed_value": None,
            "observed_text": None,
            "baseline_value": None,
            "baseline_text": None,
            "threshold_value": _as_float(rule.threshold_value),
            "threshold_text": None,
            "observed_at": latest_price.trade_date.isoformat() if latest_price else None,
            "message": "RSI 계산에 필요한 가격 데이터가 아직 부족합니다.",
            "triggered": False,
        }

    threshold = Decimal(rule.threshold_value or 0)
    is_triggered = rsi >= threshold if rule.direction == "above" else rsi <= threshold
    return {
        "rule_id": rule.id,
        "ticker": rule.stock.ticker,
        "rule_type": rule.rule_type,
        "status": "triggered" if is_triggered else "pending",
        "observed_value": round(float(rsi), 4),
        "observed_text": None,
        "baseline_value": None,
        "baseline_text": None,
        "threshold_value": round(float(threshold), 4),
        "threshold_text": None,
        "observed_at": latest_price.trade_date.isoformat(),
        "message": (
            "RSI가 설정한 임계값을 충족했습니다."
            if is_triggered
            else "RSI가 아직 임계값을 충족하지 않았습니다."
        ),
        "triggered": is_triggered,
    }


async def _evaluate_sentiment_change_rule(session: AsyncSession, rule: AlertRule) -> dict:
    lookback = max(rule.lookback_days or 2, 1)
    news_result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.stock_id == rule.stock_id,
            NewsArticle.sentiment_score.is_not(None),
        )
        .order_by(NewsArticle.published_at.desc())
        .limit(lookback * 2)
    )
    articles = news_result.scalars().all()
    if len(articles) < lookback * 2:
        return {
            "rule_id": rule.id,
            "ticker": rule.stock.ticker,
            "rule_type": rule.rule_type,
            "status": "pending",
            "observed_value": None,
            "observed_text": None,
            "baseline_value": None,
            "baseline_text": None,
            "threshold_value": _as_float(rule.threshold_value),
            "threshold_text": None,
            "observed_at": (
                articles[0].published_at.date().isoformat() if articles else None
            ),
            "message": "감성 변화 비교에 필요한 뉴스 데이터가 아직 부족합니다.",
            "triggered": False,
        }

    observed_articles = articles[:lookback]
    baseline_articles = articles[lookback : lookback * 2]
    observed_value = sum(
        Decimal(article.sentiment_score) for article in observed_articles
    ) / Decimal(lookback)
    baseline_value = sum(
        Decimal(article.sentiment_score) for article in baseline_articles
    ) / Decimal(lookback)
    delta = observed_value - baseline_value
    threshold = Decimal(rule.threshold_value or 0)
    is_triggered = delta >= threshold if rule.direction == "up" else delta <= -threshold
    return {
        "rule_id": rule.id,
        "ticker": rule.stock.ticker,
        "rule_type": rule.rule_type,
        "status": "triggered" if is_triggered else "pending",
        "observed_value": round(float(observed_value), 4),
        "observed_text": None,
        "baseline_value": round(float(baseline_value), 4),
        "baseline_text": None,
        "threshold_value": round(float(threshold), 4),
        "threshold_text": None,
        "observed_at": observed_articles[0].published_at.date().isoformat(),
        "message": (
            "최근 뉴스 감성이 기준 구간 대비 급변했습니다."
            if is_triggered
            else "최근 뉴스 감성 변화가 아직 임계값에 못 미칩니다."
        ),
        "triggered": is_triggered,
    }


async def _evaluate_recommendation_change_rule(session: AsyncSession, rule: AlertRule) -> dict:
    report_result = await session.execute(
        select(AnalysisReport)
        .where(
            AnalysisReport.stock_id == rule.stock_id,
            AnalysisReport.analysis_type == "daily",
        )
        .order_by(AnalysisReport.analysis_date.desc(), AnalysisReport.created_at.desc())
        .limit(2)
    )
    reports = report_result.scalars().all()
    if len(reports) < 2:
        return {
            "rule_id": rule.id,
            "ticker": rule.stock.ticker,
            "rule_type": rule.rule_type,
            "status": "pending",
            "observed_value": None,
            "observed_text": None,
            "baseline_value": None,
            "baseline_text": None,
            "threshold_value": None,
            "threshold_text": rule.target_recommendation,
            "observed_at": reports[0].analysis_date.isoformat() if reports else None,
            "message": "추천 변화 비교에 필요한 일일 리포트가 아직 부족합니다.",
            "triggered": False,
        }

    latest, previous = reports[0], reports[1]
    target_recommendation = _normalize_text(rule.target_recommendation)
    latest_recommendation = _normalize_text(latest.recommendation)
    previous_recommendation = _normalize_text(previous.recommendation)
    is_triggered = (
        target_recommendation is not None
        and latest_recommendation == target_recommendation
        and previous_recommendation != target_recommendation
    )
    return {
        "rule_id": rule.id,
        "ticker": rule.stock.ticker,
        "rule_type": rule.rule_type,
        "status": "triggered" if is_triggered else "pending",
        "observed_value": None,
        "observed_text": latest_recommendation,
        "baseline_value": None,
        "baseline_text": previous_recommendation,
        "threshold_value": None,
        "threshold_text": target_recommendation,
        "observed_at": latest.analysis_date.isoformat(),
        "message": (
            "최종 일일 추천이 원하는 방향으로 바뀌었습니다."
            if is_triggered
            else "최종 일일 추천이 아직 원하는 방향으로 바뀌지 않았습니다."
        ),
        "triggered": is_triggered,
    }


async def _evaluate_single_rule(session: AsyncSession, rule: AlertRule) -> dict:
    if rule.rule_type == "target_price":
        return await _evaluate_target_price_rule(session, rule)
    if rule.rule_type == "rsi_threshold":
        return await _evaluate_rsi_rule(session, rule)
    if rule.rule_type == "sentiment_change":
        return await _evaluate_sentiment_change_rule(session, rule)
    if rule.rule_type == "recommendation_change":
        return await _evaluate_recommendation_change_rule(session, rule)
    raise ValueError(f"지원하지 않는 rule_type입니다: {rule.rule_type}")


async def evaluate_alert_rules(session: AsyncSession) -> dict:
    """활성화된 개인용 알림 규칙을 평가한다."""
    rules_result = await session.execute(
        select(AlertRule)
        .options(selectinload(AlertRule.stock))
        .where(AlertRule.is_active.is_(True))
        .order_by(AlertRule.id.asc())
    )
    rules = rules_result.scalars().all()

    triggered_events: list[dict] = []
    pending_rules: list[dict] = []
    now = datetime.now(tz=KST)

    for rule in rules:
        summary = await _evaluate_single_rule(session, rule)
        summary.pop("triggered", None)
        rule.last_evaluated_at = now

        if summary["status"] != "triggered":
            pending_rules.append(summary)
            continue

        dedupe_key = _build_dedupe_key(summary)
        existing_event = await session.execute(
            select(AlertEvent).where(AlertEvent.dedupe_key == dedupe_key)
        )
        if existing_event.scalar_one_or_none() is not None:
            continue

        event = AlertEvent(
            rule_id=rule.id,
            stock_id=rule.stock_id,
            stock=rule.stock,
            rule_type=rule.rule_type,
            status="triggered",
            observed_value=(
                Decimal(str(summary["observed_value"]))
                if summary["observed_value"] is not None
                else None
            ),
            observed_text=summary["observed_text"],
            baseline_value=(
                Decimal(str(summary["baseline_value"]))
                if summary["baseline_value"] is not None
                else None
            ),
            baseline_text=summary["baseline_text"],
            threshold_value=(
                Decimal(str(summary["threshold_value"]))
                if summary["threshold_value"] is not None
                else None
            ),
            threshold_text=summary["threshold_text"],
            observed_at=_compose_observed_at_from_date(summary["observed_at"]),
            message=summary["message"],
            dedupe_key=dedupe_key,
        )
        session.add(event)
        rule.last_triggered_at = now
        await session.flush()
        triggered_events.append(_serialize_event(event))

    logger.info(
        "alert_rules_evaluated",
        evaluated_count=len(rules),
        triggered_count=len(triggered_events),
        pending_count=len(pending_rules),
    )
    return {
        "evaluated_count": len(rules),
        "triggered_count": len(triggered_events),
        "triggered_events": triggered_events,
        "pending_rules": pending_rules,
    }
