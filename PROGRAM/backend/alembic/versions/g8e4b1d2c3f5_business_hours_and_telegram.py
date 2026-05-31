"""shop business hours + telegram bot token/chat id

Revision ID: g8e4b1d2c3f5
Revises: f7d3a9c5e1b2
Create Date: 2026-05-24 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "g8e4b1d2c3f5"
down_revision = "f7d3a9c5e1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("business_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("tg_bot_token", sa.String(length=256), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("tg_chat_id", sa.String(length=64), nullable=True, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("tg_chat_id")
        batch_op.drop_column("tg_bot_token")
        batch_op.drop_column("business_hours")
