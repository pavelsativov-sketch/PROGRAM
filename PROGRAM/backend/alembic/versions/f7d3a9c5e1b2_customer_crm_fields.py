"""customer crm fields: tags, notes

Revision ID: f7d3a9c5e1b2
Revises: e8b9d2f0a1c4
Create Date: 2026-05-24 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7d3a9c5e1b2"
down_revision = "e8b9d2f0a1c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("notes")
        batch_op.drop_column("tags")
