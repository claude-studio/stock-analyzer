"""종목 관계 온톨로지 테이블

Revision ID: 003
Revises: 002
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_relations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_stock_id", sa.Integer(), nullable=False),
        sa.Column("target_stock_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("strength", sa.Numeric(4, 3), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="llm"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["source_stock_id"], ["stocks.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_stock_id"], ["stocks.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_stock_relations_pair",
        "stock_relations",
        ["source_stock_id", "relation_type", "target_stock_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_stock_relations_pair", table_name="stock_relations")
    op.drop_table("stock_relations")
