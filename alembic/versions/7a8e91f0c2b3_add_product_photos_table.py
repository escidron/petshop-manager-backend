"""add_product_photos_table

Revision ID: 7a8e91f0c2b3
Revises: 6a6bf63c2ccd
Create Date: 2026-09-04 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8e91f0c2b3'
down_revision: Union[str, Sequence[str], None] = '6a6bf63c2ccd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('photo_url', sa.String(length=500), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_photos_tenant_id'), 'product_photos', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_product_photos_product_id'), 'product_photos', ['product_id'], unique=False)

    # Enable and configure RLS
    op.execute("ALTER TABLE product_photos ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE product_photos FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON product_photos
        USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON product_photos;")
    op.execute("ALTER TABLE product_photos DISABLE ROW LEVEL SECURITY;")
    op.drop_index(op.f('ix_product_photos_product_id'), table_name='product_photos')
    op.drop_index(op.f('ix_product_photos_tenant_id'), table_name='product_photos')
    op.drop_table('product_photos')
