"""change quantities to numeric

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-12 12:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "quantity",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=10, scale=3),
        existing_nullable=False,
    )
    op.alter_column(
        "products",
        "min_stock",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=10, scale=3),
        existing_nullable=False,
    )
    op.alter_column(
        "inventory_logs",
        "quantity_change",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=10, scale=3),
        existing_nullable=False,
    )
    op.alter_column(
        "sale_items",
        "quantity",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=10, scale=3),
        existing_nullable=False,
    )
    op.alter_column(
        "comanda_items",
        "quantity",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=10, scale=3),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "comanda_items",
        "quantity",
        existing_type=sa.Numeric(precision=10, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "sale_items",
        "quantity",
        existing_type=sa.Numeric(precision=10, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "inventory_logs",
        "quantity_change",
        existing_type=sa.Numeric(precision=10, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "products",
        "min_stock",
        existing_type=sa.Numeric(precision=10, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "products",
        "quantity",
        existing_type=sa.Numeric(precision=10, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
    )
