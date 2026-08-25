"""add_whatsapp_packages_to_subscriptions

Revision ID: fa1b2c3d4e5f
Revises: f347ce0e45d2
Create Date: 2026-08-24 21:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = 'f347ce0e45d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS whatsapp_package_id VARCHAR(50);")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS whatsapp_package_status VARCHAR(30) NOT NULL DEFAULT 'inactive';")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS whatsapp_messages_limit INTEGER NOT NULL DEFAULT 0;")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS whatsapp_messages_used INTEGER NOT NULL DEFAULT 0;")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS whatsapp_period_end TIMESTAMP WITH TIME ZONE;")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS pagarme_whatsapp_subscription_id VARCHAR(100);")
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS billing_day INTEGER NOT NULL DEFAULT 1;")


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS billing_day;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS pagarme_whatsapp_subscription_id;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS whatsapp_period_end;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS whatsapp_messages_used;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS whatsapp_messages_limit;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS whatsapp_package_status;")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS whatsapp_package_id;")
