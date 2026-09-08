"""add_payroll_profiles_table

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-07 20:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create employee_payroll_profiles
    op.create_table(
        'employee_payroll_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('base_salary', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('thirteenth_salary', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('vacation_provision', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('fgts_amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('inss_amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('transport_voucher', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('food_voucher', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('meal_voucher', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('health_insurance', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('other_benefits', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('other_benefits_description', sa.String(length=255), nullable=True),
        sa.Column('custom_benefits', sa.JSON(), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', name='uq_payroll_profile_tenant_employee')
    )
    op.create_index('ix_payroll_profile_tenant_id', 'employee_payroll_profiles', ['tenant_id'], unique=False)
    op.create_index('ix_payroll_profile_employee_id', 'employee_payroll_profiles', ['employee_id'], unique=False)

    # 2. Enable RLS on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        table = "employee_payroll_profiles"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON employee_payroll_profiles;")

    op.drop_table('employee_payroll_profiles')
