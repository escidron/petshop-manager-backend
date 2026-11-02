"""add_recurrence_to_daycare_stays

Revision ID: 9a1b2c3d4e5f
Revises: 8f2a1b3c4d5e
Create Date: 2026-11-01 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '8f2a1b3c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE daycare_stays 
        ADD COLUMN IF NOT EXISTS recurrence_id VARCHAR(50),
        ADD COLUMN IF NOT EXISTS recurrence_rule JSON;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_recurrence_id ON daycare_stays (recurrence_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_daycare_stays_recurrence_id;")
    op.execute("""
        ALTER TABLE daycare_stays 
        DROP COLUMN IF EXISTS recurrence_rule,
        DROP COLUMN IF EXISTS recurrence_id;
    """)

