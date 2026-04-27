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
    portfolio_holdings: Mapped[list["PortfolioHolding"]] = relationship(back_populates="stock")


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
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    sentiment_label: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    news_category: Mapped[str | None] = mapped_column(String(20))
    impact_summary: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(String(30))
    impact_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    stock: Mapped["Stock | None"] = relationship(back_populates="news_articles")
    stock_impacts: Mapped[list["NewsStockImpact"]] = relationship(
        back_populates="news_article", cascade="all, delete-orphan"
    )


class NewsStockImpact(Base):
    """뉴스-종목 영향 분석 매핑 (M:N)."""

    __tablename__ = "news_stock_impacts"
    __table_args__ = (
        Index("ix_news_stock_impacts_news_stock", "news_article_id", "stock_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    news_article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    impact_direction: Mapped[str] = mapped_column(String(10))
    impact_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reason: Mapped[str | None] = mapped_column(Text)
    effective_trading_date: Mapped[date | None] = mapped_column(Date)
    window_label: Mapped[str | None] = mapped_column(String(20))
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20))
    stock_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    benchmark_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    abnormal_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    car: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    observed_windows: Mapped[list[dict] | None] = mapped_column(JSON)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confounded: Mapped[bool] = mapped_column(default=False)
    data_status: Mapped[str | None] = mapped_column(String(30))
    marker_label: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    news_article: Mapped["NewsArticle"] = relationship(back_populates="stock_impacts")
    stock: Mapped["Stock"] = relationship()


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


class AccuracyTracker(Base):
    """추천 적중률 추적 테이블."""

    __tablename__ = "accuracy_tracker"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_report_id: Mapped[int] = mapped_column(ForeignKey("analysis_reports.id"))
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    recommendation: Mapped[str] = mapped_column(String(20))  # strong_buy/buy/hold/sell/strong_sell
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # 분석 당일 종가
    actual_price_7d: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_price_30d: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_return_7d: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))  # 수익률 (소수)
    actual_return_30d: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    is_hit_7d: Mapped[bool | None]  # 추천 방향과 실제 방향 일치 여부
    is_hit_30d: Mapped[bool | None]
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    analysis_report: Mapped["AnalysisReport"] = relationship()


class StockRelation(Base):
    """종목 간 관계 그래프."""

    __tablename__ = "stock_relations"
    __table_args__ = (
        Index(
            "ix_stock_relations_pair",
            "source_stock_id",
            "relation_type",
            "target_stock_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    target_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(20))
    strength: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    context: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="llm")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_stock: Mapped["Stock"] = relationship(foreign_keys=[source_stock_id])
    target_stock: Mapped["Stock"] = relationship(foreign_keys=[target_stock_id])


class PortfolioHolding(Base):
    """단일 사용자 수동 포트폴리오 보유 종목."""

    __tablename__ = "portfolio_holdings"
    __table_args__ = (Index("ix_portfolio_holdings_stock_id", "stock_id", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    average_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="portfolio_holdings")
