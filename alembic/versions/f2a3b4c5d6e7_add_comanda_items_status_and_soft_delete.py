"""add_comanda_items_status_and_soft_delete

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-18 22:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add soft-delete and traceability columns to comanda_items
    op.add_column(
        'comanda_items',
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False)
    )
    op.add_column(
        'comanda_items',
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'comanda_items',
        sa.Column('removed_by_user_id', sa.Integer(), nullable=True)
    )
    op.add_column(
        'comanda_items',
        sa.Column('removal_reason', sa.Text(), nullable=True)
    )

    op.create_foreign_key(
        'fk_comanda_items_removed_by_user_id',
        'comanda_items',
        'users',
        ['removed_by_user_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        op.f('ix_comanda_items_status'),
        'comanda_items',
        ['status'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_comanda_items_status'), table_name='comanda_items')
    op.drop_constraint('fk_comanda_items_removed_by_user_id', 'comanda_items', type_='foreignkey')
    op.drop_column('comanda_items', 'removal_reason')
    op.drop_column('comanda_items', 'removed_by_user_id')
    op.drop_column('comanda_items', 'removed_at')
    op.drop_column('comanda_items', 'status')
