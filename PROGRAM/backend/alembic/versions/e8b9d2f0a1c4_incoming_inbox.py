"""incoming_messages inbox table

Revision ID: e8b9d2f0a1c4
Revises: d6a8c0f1b2e3
Create Date: 2026-05-23 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e8b9d2f0a1c4"
down_revision = "d6a8c0f1b2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incoming_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("customer_name", sa.String(length=255), server_default=""),
        sa.Column("text", sa.Text(), server_default=""),
        sa.Column("status", sa.String(length=16), server_default="pending", index=True),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.String(length=512), server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_inbox_status_received", "incoming_messages", ["status", "received_at"])
    op.create_index("ix_inbox_shop_status", "incoming_messages", ["shop_id", "status"])
    op.create_index("ix_incoming_messages_shop_id", "incoming_messages", ["shop_id"])


def downgrade() -> None:
    op.drop_index("ix_incoming_messages_shop_id", table_name="incoming_messages")
    op.drop_index("ix_inbox_shop_status", table_name="incoming_messages")
    op.drop_index("ix_inbox_status_received", table_name="incoming_messages")
    op.drop_table("incoming_messages")
