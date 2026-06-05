"""add email to tenants

Revision ID: c9d1e2f3a4b5
Revises: e7f3a812b4c9
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'e7f3a812b4c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('email', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'email')
