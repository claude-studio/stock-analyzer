"""API Key 인증 및 Rate Limiting 모듈."""

from collections import defaultdict
from time import time

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

RATE_LIMIT = 30  # 분당 최대 요청 수
RATE_WINDOW = 60  # 초

_request_counts: dict[str, list[float]] = defaultdict(list)


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """API Key 검증. settings.API_KEY가 비어있으면 인증 비활성화."""
    if not settings.API_KEY:
        return "dev-mode"
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


async def check_rate_limit(api_key: str = Depends(verify_api_key)) -> str:
    """인메모리 rate limiter. 분당 RATE_LIMIT 초과 시 429 반환."""
    now = time()
    _request_counts[api_key] = [
        t for t in _request_counts[api_key] if now - t < RATE_WINDOW
    ]
    if len(_request_counts[api_key]) >= RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    _request_counts[api_key].append(now)
    return api_key
