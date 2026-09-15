"""add_financial_bills_table

Revision ID: 61bc999a98e7
Revises: f8157ddc003a
Create Date: 2026-09-14 18:01:28.728764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61bc999a98e7'
down_revision: Union[str, Sequence[str], None] = 'f8157ddc003a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'financial_bills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bill_type', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('dre_accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('paid_amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('fine_or_interest_amount', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('issue_date', sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('document_number', sa.String(length=100), nullable=True),
        sa.Column('barcode', sa.String(length=150), nullable=True),
        sa.Column('installment_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('total_installments', sa.Integer(), server_default='1', nullable=False),
        sa.Column('parent_bill_id', sa.Integer(), sa.ForeignKey('financial_bills.id', ondelete='SET NULL'), nullable=True),
        sa.Column('destination_account_id', sa.Integer(), sa.ForeignKey('cash_destination_accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_financial_bills_tenant_id', 'financial_bills', ['tenant_id'], unique=False)
    op.create_index('ix_financial_bills_bill_type', 'financial_bills', ['bill_type'], unique=False)
    op.create_index('ix_financial_bills_status', 'financial_bills', ['status'], unique=False)
    op.create_index('ix_financial_bills_due_date', 'financial_bills', ['due_date'], unique=False)
    op.create_index('ix_financial_bills_tenant_type_status', 'financial_bills', ['tenant_id', 'bill_type', 'status'], unique=False)
    op.create_index('ix_financial_bills_tenant_due_date', 'financial_bills', ['tenant_id', 'due_date'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        table = "financial_bills"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
        """)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON financial_bills;")
    op.drop_table('financial_bills')
