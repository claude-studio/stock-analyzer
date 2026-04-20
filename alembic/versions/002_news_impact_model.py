"""뉴스 영향 분석 모델 확장

Revision ID: 002
Revises: 001
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NewsArticle 컬럼 추가
    op.add_column("news_articles", sa.Column("news_category", sa.String(20), nullable=True))
    op.add_column("news_articles", sa.Column("impact_summary", sa.Text(), nullable=True))
    op.add_column("news_articles", sa.Column("sector", sa.String(30), nullable=True))
    op.add_column("news_articles", sa.Column("impact_score", sa.Numeric(4, 3), nullable=True))

    # NewsStockImpact 테이블 생성
    op.create_table(
        "news_stock_impacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("news_article_id", sa.BigInteger(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("impact_direction", sa.String(10), nullable=False),
        sa.Column("impact_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["news_article_id"], ["news_articles.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"], ["stocks.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_news_stock_impacts_news_stock",
        "news_stock_impacts",
        ["news_article_id", "stock_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_news_stock_impacts_news_stock", table_name="news_stock_impacts")
    op.drop_table("news_stock_impacts")

    op.drop_column("news_articles", "impact_score")
    op.drop_column("news_articles", "sector")
    op.drop_column("news_articles", "impact_summary")
    op.drop_column("news_articles", "news_category")
