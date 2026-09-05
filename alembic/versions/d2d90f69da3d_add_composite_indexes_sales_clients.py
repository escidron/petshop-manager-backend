"""add_composite_indexes_sales_clients

Revision ID: d2d90f69da3d
Revises: 7a8e91f0c2b3
Create Date: 2026-09-04 21:27:03.594721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2d90f69da3d'
down_revision: Union[str, Sequence[str], None] = '7a8e91f0c2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_sales_tenant_created_at",
        "sales",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_clients_tenant_created_at",
        "clients",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_clients_tenant_created_at", table_name="clients")
    op.drop_index("ix_sales_tenant_created_at", table_name="sales")
