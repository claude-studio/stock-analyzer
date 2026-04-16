"""Telegram Bot API 유틸리티."""

from datetime import datetime, timezone, timedelta

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_MAX_LENGTH = 4096
KST = timezone(timedelta(hours=9))


async def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """Telegram 메시지 전송.

    settings.TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 비어있으면 skip.
    전송 실패 시 False 반환 (예외 전파 안 함).
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.debug("telegram_skip", reason="token 또는 chat_id 미설정")
        return False

    text = message[:TELEGRAM_MAX_LENGTH] if len(message) > TELEGRAM_MAX_LENGTH else message
    url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("telegram_send_failed", error=str(exc))
        return False


async def send_analysis_alert(
    ticker: str,
    name: str,
    recommendation: str,
    confidence: float,
    summary: str,
    key_factors: list[str] | None = None,
) -> bool:
    """종목 분석 알림 (buy/strong_buy일 때만 호출 권장)."""
    lines = [
        f"<b>\U0001f4c8 {ticker} {name}</b>",
        f"<b>추천:</b> {recommendation} (확신도: {confidence:.0%})",
        "",
        summary,
    ]

    if key_factors:
        lines.append("")
        lines.append("<b>핵심 요인:</b>")
        for factor in key_factors:
            lines.append(f"\u2022 {factor}")

    return await send_telegram("\n".join(lines))


async def send_market_summary(summary: str) -> bool:
    """일일 시장 요약 전송."""
    today = datetime.now(tz=KST).strftime("%Y-%m-%d")
    text = (
        f"<b>\U0001f4ca 일일 시장 요약</b>\n"
        f"<i>{today}</i>\n"
        f"\n"
        f"{summary}"
    )
    return await send_telegram(text)
