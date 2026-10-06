"""add appointment_item_service_employees table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-06 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appointment_item_service_employees",
        sa.Column("appointment_item_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["appointment_item_id"],
            ["appointment_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_item_id", "service_id"],
            ["appointment_item_services.appointment_item_id", "appointment_item_services.service_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("appointment_item_id", "service_id", "employee_id"),
    )

    # Migra dados existentes de appointment_item_services para appointment_item_service_employees
    op.execute(
        """
        INSERT INTO appointment_item_service_employees (appointment_item_id, service_id, employee_id)
        SELECT appointment_item_id, service_id, employee_id
        FROM appointment_item_services
        WHERE employee_id IS NOT NULL
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("appointment_item_service_employees")
