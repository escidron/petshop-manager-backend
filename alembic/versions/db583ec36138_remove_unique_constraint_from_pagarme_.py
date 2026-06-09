"""remove_unique_constraint_from_pagarme_customer_id

Revision ID: db583ec36138
Revises: 9a50a75ae447
Create Date: 2026-06-08 22:45:24.060266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db583ec36138'
down_revision: Union[str, Sequence[str], None] = '9a50a75ae447'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove a constraint de forma segura caso o nome mude ou ela não exista localmente
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_pagarme_customer_id_key")


def downgrade() -> None:
    op.create_unique_constraint('tenants_pagarme_customer_id_key', 'tenants', ['pagarme_customer_id'])
