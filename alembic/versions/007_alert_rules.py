"""개인용 알림 규칙 및 이벤트 테이블 추가

Revision ID: 007
Revises: 006
Create Date: 2026-04-27
"""

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rule_type", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=True),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("target_recommendation", sa.String(length=20), nullable=True),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_rule_type", "alert_rules", ["rule_type"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("observed_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("observed_text", sa.String(length=50), nullable=True),
        sa.Column("baseline_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("baseline_text", sa.String(length=50), nullable=True),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("threshold_text", sa.String(length=50), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_dedupe_key", "alert_events", ["dedupe_key"], unique=True)
    op.create_index(
        "ix_alert_events_rule_created",
        "alert_events",
        ["rule_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_rule_created", table_name="alert_events")
    op.drop_index("ix_alert_events_dedupe_key", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alert_rules_rule_type", table_name="alert_rules")
    op.drop_table("alert_rules")
