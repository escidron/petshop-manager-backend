"""add_vigencia_to_employees

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f
Create Date: 2026-09-16 15:47:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b7c8d9e0f1a'
down_revision: Union[str, Sequence[str], None] = '5a6b7c8d9e0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('admission_date', sa.Date(), nullable=True)
    )
    op.add_column(
        'employees',
        sa.Column('resignation_date', sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('employees', 'resignation_date')
    op.drop_column('employees', 'admission_date')
