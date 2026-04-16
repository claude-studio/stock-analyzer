"""SQLAlchemy 2.0 ORM 모델 정의."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """모든 모델의 기본 클래스."""


class Stock(Base):
    """종목 마스터 테이블."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    market: Mapped[str] = mapped_column(index=True)
    sector: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    daily_prices: Mapped[list["DailyPrice"]] = relationship(back_populates="stock")
    news_articles: Mapped[list["NewsArticle"]] = relationship(back_populates="stock")
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(back_populates="stock")


class DailyPrice(Base):
    """일별 시세 테이블."""

    __tablename__ = "daily_prices"
    __table_args__ = (
        Index("ix_daily_prices_stock_date", "stock_id", "trade_date", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    volume: Mapped[int] = mapped_column(BigInteger)
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    foreign_ratio: Mapped[Decimal | None] = mapped_column(Numeric)
    inst_net_buy: Mapped[int | None] = mapped_column(BigInteger)
    foreign_net_buy: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="daily_prices")


class NewsArticle(Base):
    """뉴스 기사 테이블."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"))
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    sentiment_label: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock | None"] = relationship(back_populates="news_articles")


class AnalysisReport(Base):
    """분석 리포트 테이블."""

    __tablename__ = "analysis_reports"
    __table_args__ = (
        Index(
            "ix_analysis_reports_stock_date_type",
            "stock_id",
            "analysis_date",
            "analysis_type",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    analysis_date: Mapped[date] = mapped_column(Date)
    analysis_type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    key_factors: Mapped[dict | None] = mapped_column(JSON)
    bull_case: Mapped[str | None] = mapped_column(Text)
    bear_case: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="analysis_reports")


class CollectionLog(Base):
    """데이터 수집 로그 테이블."""

    __tablename__ = "collection_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10))
    target_date: Mapped[date | None] = mapped_column(Date)
    stocks_count: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
