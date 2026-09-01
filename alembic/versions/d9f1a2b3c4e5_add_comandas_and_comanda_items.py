"""add_comandas_and_comanda_items

Revision ID: d9f1a2b3c4e5
Revises: 4f9b786ec5ff
Create Date: 2026-08-31 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'd9f1a2b3c4e5'
down_revision: Union[str, Sequence[str], None] = '4f9b786ec5ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create comandas table
    op.create_table(
        "comandas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comandas_tenant_id"), "comandas", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_comandas_client_id"), "comandas", ["client_id"], unique=False)
    op.create_index(op.f("ix_comandas_appointment_id"), "comandas", ["appointment_id"], unique=False)
    op.create_index(op.f("ix_comandas_status"), "comandas", ["status"], unique=False)
    op.create_index(op.f("ix_comandas_created_at"), "comandas", ["created_at"], unique=False)

    # 2. Create comanda_items table
    op.create_table(
        "comanda_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("comanda_id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("pet_ids", sa.JSON(), nullable=True),
        sa.Column("client_package_id_to_pay", sa.Integer(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True, server_default="UN"),
        sa.ForeignKeyConstraint(["comanda_id"], ["comandas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comanda_items_comanda_id"), "comanda_items", ["comanda_id"], unique=False)

    # 3. Add comanda_id to sales table
    op.add_column("sales", sa.Column("comanda_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_sales_comanda_id", "sales", "comandas", ["comanda_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_sales_comanda_id"), "sales", ["comanda_id"], unique=False)


def downgrade() -> None:
    op.drop_constraint("fk_sales_comanda_id", "sales", type_="foreignkey")
    op.drop_index(op.f("ix_sales_comanda_id"), table_name="sales")
    op.drop_column("sales", "comanda_id")

    op.drop_index(op.f("ix_comanda_items_comanda_id"), table_name="comanda_items")
    op.drop_table("comanda_items")

    op.drop_index(op.f("ix_comandas_created_at"), table_name="comandas")
    op.drop_index(op.f("ix_comandas_status"), table_name="comandas")
    op.drop_index(op.f("ix_comandas_appointment_id"), table_name="comandas")
    op.drop_index(op.f("ix_comandas_client_id"), table_name="comandas")
    op.drop_index(op.f("ix_comandas_tenant_id"), table_name="comandas")
    op.drop_table("comandas")
