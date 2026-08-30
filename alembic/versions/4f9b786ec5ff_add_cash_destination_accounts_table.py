"""add_cash_destination_accounts_table

Revision ID: 4f9b786ec5ff
Revises: c9a79b8435e0
Create Date: 2026-08-30 13:08:41.167741

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f9b786ec5ff'
down_revision: Union[str, Sequence[str], None] = 'c9a79b8435e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cash_destination_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False, server_default="internal_cash"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_destination_accounts_tenant_id"), "cash_destination_accounts", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cash_destination_accounts_tenant_id"), table_name="cash_destination_accounts")
    op.drop_table("cash_destination_accounts")
