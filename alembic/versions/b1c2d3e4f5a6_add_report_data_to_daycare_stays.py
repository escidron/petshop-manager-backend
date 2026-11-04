"""add_report_data_to_daycare_stays

Revision ID: b1c2d3e4f5a6
Revises: 9a1b2c3d4e5f
Create Date: 2026-11-02 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE daycare_stays 
        ADD COLUMN IF NOT EXISTS report_data JSON;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE daycare_stays 
        DROP COLUMN IF EXISTS report_data;
    """)

