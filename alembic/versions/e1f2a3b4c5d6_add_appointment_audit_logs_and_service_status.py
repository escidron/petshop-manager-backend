"""add_appointment_audit_logs_and_service_status

Revision ID: e1f2a3b4c5d6
Revises: 6b7c8d9e0f1a
Create Date: 2026-09-18 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = '6b7c8d9e0f1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add status and audit columns to appointment_item_services
    op.add_column(
        'appointment_item_services',
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False)
    )
    op.add_column(
        'appointment_item_services',
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'appointment_item_services',
        sa.Column('removed_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    )
    op.add_column(
        'appointment_item_services',
        sa.Column('removal_reason', sa.String(length=255), nullable=True)
    )

    # 2. Create appointment_audit_logs table
    op.create_table(
        'appointment_audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('appointment_item_id', sa.Integer(), nullable=True),
        sa.Column('service_id', sa.Integer(), nullable=True),
        sa.Column('service_name', sa.String(length=150), nullable=True),
        sa.Column('pet_id', sa.Integer(), nullable=True),
        sa.Column('pet_name', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # 3. Enable RLS on appointment_audit_logs
    try:
        op.execute("ALTER TABLE appointment_audit_logs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE appointment_audit_logs FORCE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_policy ON appointment_audit_logs
            USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
        """)
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON appointment_audit_logs;")
    except Exception:
        pass
    op.drop_table('appointment_audit_logs')
    op.drop_column('appointment_item_services', 'removal_reason')
    op.drop_column('appointment_item_services', 'removed_by_user_id')
    op.drop_column('appointment_item_services', 'removed_at')
    op.drop_column('appointment_item_services', 'status')
