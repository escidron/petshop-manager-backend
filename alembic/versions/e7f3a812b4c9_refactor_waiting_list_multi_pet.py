"""refactor waiting list to support multiple pets per entry

Revision ID: e7f3a812b4c9
Revises: da4da459672d
Create Date: 2026-06-02 16:43:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f3a812b4c9'
down_revision: Union[str, Sequence[str], None] = 'da4da459672d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: replace single-pet waiting list with multi-pet items."""
    # 1. Drop the old waiting_list_services table (was linked to waiting_list_entries directly)
    op.drop_table('waiting_list_services')

    # 2. Create the new waiting_list_items table
    op.create_table(
        'waiting_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('waiting_list_entry_id', sa.Integer(), nullable=False),
        sa.Column('pet_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['waiting_list_entry_id'], ['waiting_list_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pet_id'], ['pets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Recreate waiting_list_services linked to waiting_list_items
    op.create_table(
        'waiting_list_services',
        sa.Column('waiting_list_item_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['waiting_list_item_id'], ['waiting_list_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('waiting_list_item_id', 'service_id')
    )

    # 4. Remove the pet_id column from waiting_list_entries
    op.drop_constraint('waiting_list_entries_pet_id_fkey', 'waiting_list_entries', type_='foreignkey')
    op.drop_column('waiting_list_entries', 'pet_id')


def downgrade() -> None:
    """Downgrade schema: restore old single-pet waiting list structure."""
    # 1. Restore pet_id on waiting_list_entries
    op.add_column('waiting_list_entries', sa.Column('pet_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'waiting_list_entries_pet_id_fkey',
        'waiting_list_entries',
        'pets',
        ['pet_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 2. Drop new waiting_list_services and waiting_list_items
    op.drop_table('waiting_list_services')
    op.drop_table('waiting_list_items')

    # 3. Recreate old waiting_list_services linked directly to entries
    op.create_table(
        'waiting_list_services',
        sa.Column('waiting_list_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['waiting_list_id'], ['waiting_list_entries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('waiting_list_id', 'service_id')
    )
