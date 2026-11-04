"""create_daycare_packages

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-11-03 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS daycare_packages (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            price_cents INTEGER NOT NULL DEFAULT 0,
            is_monthly BOOLEAN NOT NULL DEFAULT TRUE,
            frequency INTEGER,
            days_quantity INTEGER,
            validity_days INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_daycare_packages_tenant_id ON daycare_packages (tenant_id);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS daycare_packages;
    """)

