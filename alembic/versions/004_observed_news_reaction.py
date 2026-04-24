"""뉴스 영향 관측 가격 반응 필드 추가

Revision ID: 004
Revises: 003
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_stock_impacts", sa.Column("effective_trading_date", sa.Date(), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("window_label", sa.String(20), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("benchmark_ticker", sa.String(20), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("stock_return", sa.Numeric(10, 6), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("benchmark_return", sa.Numeric(10, 6), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("abnormal_return", sa.Numeric(10, 6), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("car", sa.Numeric(10, 6), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("observed_windows", sa.JSON(), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column(
        "news_stock_impacts",
        sa.Column("confounded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("news_stock_impacts", sa.Column("data_status", sa.String(30), nullable=True))
    op.add_column("news_stock_impacts", sa.Column("marker_label", sa.String(80), nullable=True))
    op.create_index(
        "ix_news_stock_impacts_stock_effective_date",
        "news_stock_impacts",
        ["stock_id", "effective_trading_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_news_stock_impacts_stock_effective_date", table_name="news_stock_impacts")
    op.drop_column("news_stock_impacts", "marker_label")
    op.drop_column("news_stock_impacts", "data_status")
    op.drop_column("news_stock_impacts", "confounded")
    op.drop_column("news_stock_impacts", "confidence")
    op.drop_column("news_stock_impacts", "car")
    op.drop_column("news_stock_impacts", "observed_windows")
    op.drop_column("news_stock_impacts", "abnormal_return")
    op.drop_column("news_stock_impacts", "benchmark_return")
    op.drop_column("news_stock_impacts", "stock_return")
    op.drop_column("news_stock_impacts", "benchmark_ticker")
    op.drop_column("news_stock_impacts", "window_label")
    op.drop_column("news_stock_impacts", "effective_trading_date")
