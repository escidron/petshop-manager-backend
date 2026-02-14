"""add unique index with coalesce for services 2

Revision ID: 0e59c79e96b3
Revises: bc816ebb0030
Create Date: 2026-02-13 21:31:15.802913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e59c79e96b3'
down_revision: Union[str, Sequence[str], None] = 'bc816ebb0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE services
        ADD CONSTRAINT uq_service_variant
        UNIQUE NULLS NOT DISTINCT (
            tenant_id,
            name,
            species,
            size,
            coat_type
        );
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE services
        DROP CONSTRAINT IF EXISTS uq_service_variant;
    """)


