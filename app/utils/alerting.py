"""Teams Webhook 알림 모듈."""

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")


async def notify_failure(job_name: str, exc: Exception, started_at: datetime) -> None:
    """잡 실패 시 Teams Webhook으로 알림을 전송한다.

    Args:
        job_name: 실패한 잡 이름.
        exc: 발생한 예외.
        started_at: 잡 시작 시각.
    """
    if not settings.TEAMS_WEBHOOK_URL:
        return

    now = datetime.now(tz=KST)
    elapsed = (now - started_at).total_seconds()
    error_msg = str(exc)[:200]

    card_payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Stock Analyzer Job Failed",
                            "weight": "Bolder",
                            "size": "Medium",
                            "color": "Attention",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Job", "value": job_name},
                                {"title": "Error", "value": error_msg},
                                {"title": "Elapsed", "value": f"{elapsed:.1f}s"},
                                {
                                    "title": "Time (KST)",
                                    "value": now.strftime("%Y-%m-%d %H:%M:%S"),
                                },
                            ],
                        },
                    ],
                },
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.TEAMS_WEBHOOK_URL, json=card_payload)
            resp.raise_for_status()
        logger.info("failure_alert_sent", job=job_name)
    except httpx.HTTPError as alert_exc:
        logger.warning(
            "failure_alert_send_failed",
            job=job_name,
            error=str(alert_exc),
        )


async def notify_success(job_name: str, message: str) -> None:
    """선택적 성공 알림을 Teams Webhook으로 전송한다.

    Args:
        job_name: 완료된 잡 이름.
        message: 알림 메시지.
    """
    if not settings.TEAMS_WEBHOOK_URL:
        return

    now = datetime.now(tz=KST)

    card_payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Stock Analyzer Job Completed",
                            "weight": "Bolder",
                            "size": "Medium",
                            "color": "Good",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Job", "value": job_name},
                                {"title": "Message", "value": message},
                                {
                                    "title": "Time (KST)",
                                    "value": now.strftime("%Y-%m-%d %H:%M:%S"),
                                },
                            ],
                        },
                    ],
                },
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.TEAMS_WEBHOOK_URL, json=card_payload)
            resp.raise_for_status()
        logger.info("success_alert_sent", job=job_name)
    except httpx.HTTPError as alert_exc:
        logger.warning(
            "success_alert_send_failed",
            job=job_name,
            error=str(alert_exc),
        )
