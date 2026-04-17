"""Discord Webhook 알림 유틸리티."""

from datetime import datetime, timezone, timedelta

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

DISCORD_API = "https://discord.com/api/webhooks/{webhook_id}/{webhook_token}"
DISCORD_MAX_LENGTH = 2000
KST = timezone(timedelta(hours=9))
DISCLAIMER = "\n> *이 분석은 정보 제공 목적이며 투자 권유가 아닙니다.*"

_RECOMMENDATION_COLORS = {
    "strong_buy": 0x00AA00,
    "buy": 0x00FF00,
    "hold": 0xFFAA00,
    "sell": 0xFF0000,
    "strong_sell": 0xAA0000,
}


async def send_discord(
    content: str = "",
    embeds: list[dict] | None = None,
) -> bool:
    """Discord Webhook 메시지 전송.

    settings.DISCORD_WEBHOOK_URL이 비어있으면 skip. 실패 시 False.
    """
    if not settings.DISCORD_WEBHOOK_URL:
        logger.debug("discord_skip", reason="webhook_url 미설정")
        return False

    payload: dict = {}
    if content:
        payload["content"] = content[:DISCORD_MAX_LENGTH]
    if embeds:
        payload["embeds"] = embeds

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("discord_send_failed", error=str(exc))
        return False


async def send_analysis_alert(
    ticker: str,
    name: str,
    recommendation: str,
    confidence: float,
    summary: str,
    key_factors: list[str] | None = None,
) -> bool:
    """종목 분석 알림 (Discord Embed)."""
    color = _RECOMMENDATION_COLORS.get(recommendation, 0x808080)

    fields = [
        {"name": "추천", "value": recommendation, "inline": True},
        {"name": "확신도", "value": f"{confidence:.0%}", "inline": True},
    ]
    if key_factors:
        factors_text = "\n".join(f"- {f}" for f in key_factors)
        fields.append({"name": "핵심 요인", "value": factors_text, "inline": False})

    embed = {
        "title": f"{ticker} {name}",
        "description": summary,
        "color": color,
        "fields": fields,
        "footer": {"text": DISCLAIMER.strip().lstrip("> *").rstrip("*")},
    }
    return await send_discord(embeds=[embed])


async def send_market_summary(summary: str) -> bool:
    """일일 시장 요약 전송."""
    now = datetime.now(tz=KST)
    embed = {
        "title": "일일 시장 요약",
        "description": summary,
        "color": 0x0099FF,
        "timestamp": now.isoformat(),
    }
    return await send_discord(embeds=[embed])


async def send_alert(title: str, message: str, color: int = 0xFF0000) -> bool:
    """범용 알림 (에러/경고용)."""
    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": datetime.now(tz=KST).isoformat(),
    }
    return await send_discord(embeds=[embed])
