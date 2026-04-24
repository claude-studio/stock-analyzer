"""누락된 뉴스 영향 관측 반응 필드 복구

Revision ID: 005
Revises: 004
Create Date: 2026-04-24
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS effective_trading_date date
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS window_label varchar(20)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS benchmark_ticker varchar(20)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS stock_return numeric(10, 6)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS benchmark_return numeric(10, 6)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS abnormal_return numeric(10, 6)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS car numeric(10, 6)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS observed_windows json
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS confidence numeric(4, 3)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS confounded boolean NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS data_status varchar(30)
        """
    )
    op.execute(
        """
        ALTER TABLE news_stock_impacts
        ADD COLUMN IF NOT EXISTS marker_label varchar(80)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_stock_impacts_stock_effective_date
        ON news_stock_impacts (stock_id, effective_trading_date)
        """
    )


def downgrade() -> None:
    pass
