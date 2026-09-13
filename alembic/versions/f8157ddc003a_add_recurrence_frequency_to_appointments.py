"""add_recurrence_frequency_to_appointments

Revision ID: f8157ddc003a
Revises: d1a10211b55f
Create Date: 2026-09-13 14:52:21.281434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8157ddc003a'
down_revision: Union[str, Sequence[str], None] = 'd1a10211b55f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('appointments', sa.Column('recurrence_frequency', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('appointments', 'recurrence_frequency')
