"""add_permissions_to_tenant_users

Revision ID: fb1c2d3e4f5a
Revises: fa1b2c3d4e5f
Create Date: 2026-08-25 22:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'fb1c2d3e4f5a'
down_revision: Union[str, Sequence[str], None] = 'fa1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS permissions JSONB;")


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_users DROP COLUMN IF EXISTS permissions;")
