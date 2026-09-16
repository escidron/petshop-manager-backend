"""add_vigencia_to_payroll_profiles

Revision ID: 5a6b7c8d9e0f
Revises: 4d95da072ff5
Create Date: 2026-09-16 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a6b7c8d9e0f'
down_revision: Union[str, Sequence[str], None] = '4d95da072ff5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employee_payroll_profiles',
        sa.Column('admission_date', sa.Date(), nullable=True)
    )
    op.add_column(
        'employee_payroll_profiles',
        sa.Column('resignation_date', sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('employee_payroll_profiles', 'resignation_date')
    op.drop_column('employee_payroll_profiles', 'admission_date')
