"""add appointment status

Revision ID: 8c93c5ca6c14
Revises: d8e5581b2184
Create Date: 2026-01-31 19:22:04.783937
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8c93c5ca6c14'
down_revision: Union[str, Sequence[str], None] = 'd8e5581b2184'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 🔹 Definição explícita do ENUM
appointment_status_enum = postgresql.ENUM(
    'pending',
    'confirmed',
    'in_progress',
    'completed',
    'canceled',
    'no_show',
    name='appointment_status',
    create_type=False,  # importante
)


def upgrade() -> None:
    # 1️⃣ cria o tipo ENUM no banco
    appointment_status_enum.create(op.get_bind(), checkfirst=True)

    # 2️⃣ adiciona a coluna usando o tipo
    op.add_column(
        'appointments',
        sa.Column(
            'status',
            appointment_status_enum,
            nullable=False,
            server_default='pending',  # 🔥 evita erro se já existirem registros
        )
    )

    # 3️⃣ índice
    op.create_index(
        op.f('ix_appointments_status'),
        'appointments',
        ['status'],
        unique=False
    )

    # (opcional) remove o default depois
    op.alter_column('appointments', 'status', server_default=None)


def downgrade() -> None:
    # remove índice
    op.drop_index(op.f('ix_appointments_status'), table_name='appointments')

    # remove coluna
    op.drop_column('appointments', 'status')

    # remove tipo ENUM
    appointment_status_enum.drop(op.get_bind(), checkfirst=True)
