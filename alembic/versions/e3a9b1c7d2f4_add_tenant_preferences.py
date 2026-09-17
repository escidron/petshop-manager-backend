"""add tenant preferences

Revision ID: e3a9b1c7d2f4
Revises: 61bc999a98e7
Create Date: 2026-09-15 10:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a9b1c7d2f4'
down_revision: Union[str, Sequence[str], None] = '61bc999a98e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('preferences', sa.JSON(), server_default='{}', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'preferences')
