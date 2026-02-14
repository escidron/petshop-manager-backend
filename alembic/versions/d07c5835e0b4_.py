"""

Revision ID: d07c5835e0b4
Revises: c2aee5410cda
Create Date: 2026-02-13 21:19:14.230168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd07c5835e0b4'
down_revision: Union[str, Sequence[str], None] = 'c2aee5410cda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_service_variant",
        "services",
        ["tenant_id", "name", "species", "size", "coat_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_service_variant",
        "services",
        type_="unique",
    )
