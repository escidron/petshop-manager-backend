"""add_dre_financial_tables

Revision ID: 1a2b3c4d5e6f
Revises: 1780b4630f50
Create Date: 2026-09-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = '1780b4630f50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create dre_accounts
    op.create_table(
        'dre_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=True),
        sa.Column('group_type', sa.String(length=50), nullable=False),
        sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('system_source', sa.String(length=50), nullable=True),
        sa.Column('order_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dre_accounts_tenant_id', 'dre_accounts', ['tenant_id'], unique=False)
    op.create_index('ix_dre_accounts_tenant_group', 'dre_accounts', ['tenant_id', 'group_type'], unique=False)

    # 2. Create dre_entries
    op.create_table(
        'dre_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('dre_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('competence_year', sa.Integer(), nullable=False),
        sa.Column('competence_month', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'account_id', 'competence_year', 'competence_month', name='uq_dre_entry_tenant_account_period')
    )
    op.create_index('ix_dre_entries_tenant_id', 'dre_entries', ['tenant_id'], unique=False)
    op.create_index('ix_dre_entries_account_id', 'dre_entries', ['account_id'], unique=False)
    op.create_index('ix_dre_entries_tenant_period', 'dre_entries', ['tenant_id', 'competence_year', 'competence_month'], unique=False)

    # 3. Enable RLS on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ["dre_accounts", "dre_entries"]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
            """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ["dre_entries", "dre_accounts"]:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")

    op.drop_table('dre_entries')
    op.drop_table('dre_accounts')
