"""add ig_proxy

Revision ID: b9c1d2e3f4a5
Revises: ab722e9a4840
Create Date: 2026-05-10 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import app.database  # noqa


revision = 'b9c1d2e3f4a5'
down_revision = 'ab722e9a4840'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('shops') as batch_op:
        batch_op.add_column(sa.Column('ig_proxy', app.database.EncryptedString(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('shops') as batch_op:
        batch_op.drop_column('ig_proxy')
