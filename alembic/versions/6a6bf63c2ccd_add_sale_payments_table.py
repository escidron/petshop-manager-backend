"""add_sale_payments_table

Revision ID: 6a6bf63c2ccd
Revises: 568149d4dd23
Create Date: 2026-09-03 20:33:41.686029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a6bf63c2ccd'
down_revision: Union[str, Sequence[str], None] = '568149d4dd23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sale_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sale_payments_sale_id'), 'sale_payments', ['sale_id'], unique=False)

    # Backfill existing sales
    op.execute(
        """
        INSERT INTO sale_payments (sale_id, payment_method, amount, created_at)
        SELECT id, payment_method, total_amount, created_at
        FROM sales
        WHERE payment_method IS NOT NULL;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sale_payments_sale_id'), table_name='sale_payments')
    op.drop_table('sale_payments')
