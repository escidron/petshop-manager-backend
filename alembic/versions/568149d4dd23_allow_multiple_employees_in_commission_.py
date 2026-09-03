"""allow_multiple_employees_in_commission_rule

Revision ID: 568149d4dd23
Revises: d9f1a2b3c4e5
Create Date: 2026-09-01 14:16:38.551273

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '568149d4dd23'
down_revision: Union[str, Sequence[str], None] = 'd9f1a2b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'commission_rule_employees',
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['commission_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('rule_id', 'employee_id'),
    )

    op.execute(
        """
        INSERT INTO commission_rule_employees (rule_id, employee_id)
        SELECT id, employee_id FROM commission_rules WHERE employee_id IS NOT NULL
        """
    )

    op.drop_index(op.f('ix_commission_rules_employee_id'), table_name='commission_rules')
    op.drop_constraint(op.f('commission_rules_employee_id_fkey'), 'commission_rules', type_='foreignkey')
    op.drop_column('commission_rules', 'employee_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('commission_rules', sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('commission_rules_employee_id_fkey'), 'commission_rules', 'employees', ['employee_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_commission_rules_employee_id'), 'commission_rules', ['employee_id'], unique=False)
    op.drop_table('commission_rule_employees')
