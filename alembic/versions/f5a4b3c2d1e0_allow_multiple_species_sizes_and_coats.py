"""allow multiple species sizes and coats for services

Revision ID: f5a4b3c2d1e0
Revises: e6f7a8b9c0d1
Create Date: 2026-10-12 18:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f5a4b3c2d1e0"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new JSON columns
    op.add_column("services", sa.Column("species_list", sa.JSON(), nullable=True))
    op.add_column("services", sa.Column("sizes", sa.JSON(), nullable=True))
    op.add_column("services", sa.Column("coat_types", sa.JSON(), nullable=True))

    # 2. Migrate existing data from old columns into arrays
    op.execute("""
        UPDATE services SET
            species_list = CASE WHEN species IS NOT NULL THEN json_build_array(species::text) ELSE NULL END,
            sizes = CASE WHEN size IS NOT NULL THEN json_build_array(size::text) ELSE NULL END,
            coat_types = CASE WHEN coat_type IS NOT NULL THEN json_build_array(coat_type) ELSE NULL END
    """)

    # 3. Drop old columns
    op.drop_column("services", "species")
    op.drop_column("services", "size")
    op.drop_column("services", "coat_type")

    # 4. Rename species_list to species
    op.alter_column("services", "species_list", new_column_name="species")


def downgrade() -> None:
    op.add_column("services", sa.Column("species_old", sa.Enum("CANINO", "FELINO", "EXOTICOS", name="petspecies"), nullable=True))
    op.add_column("services", sa.Column("size", sa.Enum("PP", "P", "M", "G", "GG", name="petsize"), nullable=True))
    op.add_column("services", sa.Column("coat_type", sa.String(length=50), nullable=True))

    op.execute("""
        UPDATE services SET
            species_old = CASE WHEN species IS NOT NULL AND json_array_length(species) > 0 THEN (species->>0)::petspecies ELSE NULL END,
            size = CASE WHEN sizes IS NOT NULL AND json_array_length(sizes) > 0 THEN (sizes->>0)::petsize ELSE NULL END,
            coat_type = CASE WHEN coat_types IS NOT NULL AND json_array_length(coat_types) > 0 THEN coat_types->>0 ELSE NULL END
    """)

    op.drop_column("services", "species")
    op.drop_column("services", "sizes")
    op.drop_column("services", "coat_types")

    op.alter_column("services", "species_old", new_column_name="species")
