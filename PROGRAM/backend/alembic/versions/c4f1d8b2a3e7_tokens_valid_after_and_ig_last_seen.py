"""tokens_valid_after + ig_last_seen

Revision ID: c4f1d8b2a3e7
Revises: b9c1d2e3f4a5
Create Date: 2026-05-17 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f1d8b2a3e7'
down_revision = 'b9c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('shops') as batch_op:
        batch_op.add_column(sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ig_last_seen', sa.JSON(), nullable=True))
    # Заполним для существующих магазинов: tokens_valid_after = NOW (любой токен будет валиден),
    # ig_last_seen = {} (после рестарта IG-поллер обнулит на первом проходе).
    op.execute("UPDATE shops SET tokens_valid_after = CURRENT_TIMESTAMP WHERE tokens_valid_after IS NULL")
    op.execute("UPDATE shops SET ig_last_seen = '{}' WHERE ig_last_seen IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('shops') as batch_op:
        batch_op.drop_column('ig_last_seen')
        batch_op.drop_column('tokens_valid_after')
