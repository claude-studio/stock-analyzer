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
    FTC_API_KEY: str = ""
    TEAMS_WEBHOOK_URL: str = ""
    DISCORD_WEBHOOK_URL: str = ""
    API_KEY: str = ""
    MODE: str = "PRD"
    KR_WATCHLIST_RAW: str = "005930,000660,035420"
    US_WATCHLIST_RAW: str = "SPY,QQQ,AAPL"

    @property
    def KR_WATCHLIST(self) -> list[str]:
        return [s.strip() for s in self.KR_WATCHLIST_RAW.split(",") if s.strip()]

    @property
    def US_WATCHLIST(self) -> list[str]:
        return [s.strip() for s in self.US_WATCHLIST_RAW.split(",") if s.strip()]


settings = Settings()
