"""초기 스키마 생성

Revision ID: 001
Revises:
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # stocks
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("sector", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stocks_ticker", "stocks", ["ticker"], unique=True)
    op.create_index("ix_stocks_market", "stocks", ["market"])

    # daily_prices
    op.create_table(
        "daily_prices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(12, 2), nullable=False),
        sa.Column("high", sa.Numeric(12, 2), nullable=False),
        sa.Column("low", sa.Numeric(12, 2), nullable=False),
        sa.Column("close", sa.Numeric(12, 2), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.Column("foreign_ratio", sa.Numeric(), nullable=True),
        sa.Column("inst_net_buy", sa.BigInteger(), nullable=True),
        sa.Column("foreign_net_buy", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
    )
    op.create_index(
        "ix_daily_prices_stock_date",
        "daily_prices",
        ["stock_id", "trade_date"],
        unique=True,
    )

    # news_articles
    op.create_table(
        "news_articles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("sentiment_label", sa.String(10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.UniqueConstraint("url"),
    )

    # analysis_reports
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("analysis_date", sa.Date(), nullable=False),
        sa.Column("analysis_type", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("key_factors", JSON(), nullable=True),
        sa.Column("bull_case", sa.Text(), nullable=True),
        sa.Column("bear_case", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
    )
    op.create_index(
        "ix_analysis_reports_stock_date_type",
        "analysis_reports",
        ["stock_id", "analysis_date", "analysis_type"],
        unique=True,
    )

    # collection_logs
    op.create_table(
        "collection_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("stocks_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # accuracy_tracker
    op.create_table(
        "accuracy_tracker",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_report_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("recommendation", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("entry_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_price_7d", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_price_30d", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_return_7d", sa.Numeric(8, 4), nullable=True),
        sa.Column("actual_return_30d", sa.Numeric(8, 4), nullable=True),
        sa.Column("is_hit_7d", sa.Boolean(), nullable=True),
        sa.Column("is_hit_30d", sa.Boolean(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["analysis_report_id"], ["analysis_reports.id"]),
    )
    op.create_index("ix_accuracy_tracker_ticker", "accuracy_tracker", ["ticker"])


def downgrade() -> None:
    op.drop_table("accuracy_tracker")
    op.drop_table("collection_logs")
    op.drop_table("analysis_reports")
    op.drop_table("news_articles")
    op.drop_table("daily_prices")
    op.drop_table("stocks")
