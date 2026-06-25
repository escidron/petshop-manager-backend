"""add_discount_configurations

Revision ID: a377ae39f8bc
Revises: 84e3197ef8fe
Create Date: 2026-06-21 11:45:01.162944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a377ae39f8bc'
down_revision: Union[str, Sequence[str], None] = '84e3197ef8fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('allow_discount', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('tenants', sa.Column('max_discount_percentage', sa.Numeric(precision=5, scale=2), server_default='100.00', nullable=False))
    op.add_column('sales', sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sales', 'discount_amount')
    op.drop_column('tenants', 'max_discount_percentage')
    op.drop_column('tenants', 'allow_discount')
