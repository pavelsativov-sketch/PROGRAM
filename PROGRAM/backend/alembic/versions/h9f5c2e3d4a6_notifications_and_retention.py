"""notifications center, bot toggle, daily summary, customer important dates

Revision ID: h9f5c2e3d4a6
Revises: g8e4b1d2c3f5
Create Date: 2026-05-31 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "h9f5c2e3d4a6"
down_revision = "g8e4b1d2c3f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="info"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), server_default=""),
        sa.Column("link", sa.String(length=255), server_default=""),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("dedup_key", sa.String(length=128), server_default="", index=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notif_shop_created", "notifications", ["shop_id", "created_at"])
    op.create_index("ix_notif_shop_read", "notifications", ["shop_id", "read_at"])

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bot_enabled", sa.Boolean(), server_default=sa.true()))
        batch_op.add_column(sa.Column("daily_summary_hour", sa.Integer(), server_default="21"))
        batch_op.add_column(sa.Column("followup_enabled", sa.Boolean(), server_default=sa.true()))

    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("important_dates", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("important_dates")
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("followup_enabled")
        batch_op.drop_column("daily_summary_hour")
        batch_op.drop_column("bot_enabled")
    op.drop_index("ix_notif_shop_read", table_name="notifications")
    op.drop_index("ix_notif_shop_created", table_name="notifications")
    op.drop_table("notifications")
