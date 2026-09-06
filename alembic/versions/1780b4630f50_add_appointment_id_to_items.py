"""add_appointment_id_to_items

Revision ID: 1780b4630f50
Revises: d2d90f69da3d
Create Date: 2026-09-06 13:10:40.902094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1780b4630f50'
down_revision: Union[str, Sequence[str], None] = 'd2d90f69da3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('comanda_items', sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_comanda_items_appointment_id', 'comanda_items', ['appointment_id'], unique=False)
    op.add_column('sale_items', sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_sale_items_appointment_id', 'sale_items', ['appointment_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_sale_items_appointment_id', table_name='sale_items')
    op.drop_column('sale_items', 'appointment_id')
    op.drop_index('ix_comanda_items_appointment_id', table_name='comanda_items')
    op.drop_column('comanda_items', 'appointment_id')
