"""add_status_and_cancel_reason_to_sale_items

Revision ID: 4d95da072ff5
Revises: e3a9b1c7d2f4
Create Date: 2026-09-15 20:25:26.925514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d95da072ff5'
down_revision: Union[str, Sequence[str], None] = 'e3a9b1c7d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sales', sa.Column('cancel_reason', sa.String(length=255), nullable=True))
    op.add_column('sales', sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('sale_items', sa.Column('status', sa.String(length=20), server_default='active', nullable=False))
    op.add_column('sale_items', sa.Column('cancel_reason', sa.String(length=255), nullable=True))
    op.add_column('sale_items', sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sale_items', 'canceled_at')
    op.drop_column('sale_items', 'cancel_reason')
    op.drop_column('sale_items', 'status')

    op.drop_column('sales', 'canceled_at')
    op.drop_column('sales', 'cancel_reason')
