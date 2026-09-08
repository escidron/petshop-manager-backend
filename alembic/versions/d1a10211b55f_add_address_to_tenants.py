"""add_address_to_tenants

Revision ID: d1a10211b55f
Revises: 2b3c4d5e6f7a
Create Date: 2026-09-08 15:50:19.631972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a10211b55f'
down_revision: Union[str, Sequence[str], None] = '2b3c4d5e6f7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('cep', sa.String(length=10), nullable=True))
    op.add_column('tenants', sa.Column('street', sa.String(length=150), nullable=True))
    op.add_column('tenants', sa.Column('number', sa.String(length=20), nullable=True))
    op.add_column('tenants', sa.Column('complement', sa.String(length=100), nullable=True))
    op.add_column('tenants', sa.Column('neighborhood', sa.String(length=100), nullable=True))
    op.add_column('tenants', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('tenants', sa.Column('state', sa.String(length=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'state')
    op.drop_column('tenants', 'city')
    op.drop_column('tenants', 'neighborhood')
    op.drop_column('tenants', 'complement')
    op.drop_column('tenants', 'number')
    op.drop_column('tenants', 'street')
    op.drop_column('tenants', 'cep')
