"""add product_ids to commission_rules

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-08 20:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commission_rules",
        sa.Column("product_ids", sa.JSON(), nullable=True, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("commission_rules", "product_ids")
