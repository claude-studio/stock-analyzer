"""애플리케이션 설정 모듈."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수 기반 애플리케이션 설정."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    POSTGRES_DSN: str = "postgresql+asyncpg://stock:stock_pass@boj-postgres:5432/stock_analysis"
    REDIS_URL: str = "redis://stock-redis:6379/0"
    CLAUDE_PATH: str = "/usr/bin/claude"
    CLAUDE_TIMEOUT: int = 120
    DART_API_KEY: str = ""
    TEAMS_WEBHOOK_URL: str = ""
    MODE: str = "PRD"
    KR_WATCHLIST: list[str] = ["005930", "000660", "035420"]
    US_WATCHLIST: list[str] = ["SPY", "QQQ", "AAPL"]

    @field_validator("KR_WATCHLIST", "US_WATCHLIST", mode="before")
    @classmethod
    def parse_comma_separated(cls, v: str | list[str]) -> list[str]:
        """쉼표 구분 문자열을 리스트로 파싱."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
