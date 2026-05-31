"""kaspi settings and product media

Revision ID: d6a8c0f1b2e3
Revises: c4f1d8b2a3e7
Create Date: 2026-05-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d6a8c0f1b2e3"
down_revision = "c4f1d8b2a3e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kaspi_phone", sa.String(length=32), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("kaspi_name", sa.String(length=255), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("kaspi_qr_url", sa.String(length=512), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("payment_instructions", sa.Text(), nullable=True, server_default=""))

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=128), nullable=True, server_default="Bouquets"))
        batch_op.add_column(sa.Column("available_today", sa.Boolean(), nullable=True, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("available_today")
        batch_op.drop_column("category")

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("payment_instructions")
        batch_op.drop_column("kaspi_qr_url")
        batch_op.drop_column("kaspi_name")
        batch_op.drop_column("kaspi_phone")
