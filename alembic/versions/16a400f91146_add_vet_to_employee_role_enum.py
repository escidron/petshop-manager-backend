"""add vet to employee_role enum

Revision ID: 16a400f91146
Revises: ee31ca0e2e6a
Create Date: 2026-08-03 00:12:51.026623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16a400f91146'
down_revision: Union[str, Sequence[str], None] = 'ee31ca0e2e6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE employee_role ADD VALUE IF NOT EXISTS 'vet'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
