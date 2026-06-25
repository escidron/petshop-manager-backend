"""add_client_package_usages

Revision ID: 05b316f699fc
Revises: a377ae39f8bc
Create Date: 2026-06-21 12:55:52.931468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05b316f699fc'
down_revision: Union[str, Sequence[str], None] = 'a377ae39f8bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('client_package_usages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('client_package_id', sa.Integer(), nullable=False),
    sa.Column('credit_id', sa.Integer(), nullable=False),
    sa.Column('change_qty', sa.Integer(), nullable=False),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['client_package_id'], ['client_packages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['credit_id'], ['client_package_credits.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_client_package_usages_client_package_id'), 'client_package_usages', ['client_package_id'], unique=False)
    op.create_index(op.f('ix_client_package_usages_credit_id'), 'client_package_usages', ['credit_id'], unique=False)
    op.create_index(op.f('ix_client_package_usages_tenant_id'), 'client_package_usages', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_client_package_usages_tenant_id'), table_name='client_package_usages')
    op.drop_index(op.f('ix_client_package_usages_credit_id'), table_name='client_package_usages')
    op.drop_index(op.f('ix_client_package_usages_client_package_id'), table_name='client_package_usages')
    op.drop_table('client_package_usages')
