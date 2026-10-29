"""add_whatsapp_message_tracking_fields

Revision ID: 687d791cc20b
Revises: 770eb4424557
Create Date: 2026-10-26 21:10:53.420897

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '687d791cc20b'
down_revision: Union[str, Sequence[str], None] = '770eb4424557'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE whatsapp_messages 
        ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'sent' NOT NULL,
        ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(50),
        ADD COLUMN IF NOT EXISTS meta_message_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS error_message TEXT,
        ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0 NOT NULL;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_whatsapp_messages_meta_message_id ON whatsapp_messages (meta_message_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_whatsapp_messages_trigger_type ON whatsapp_messages (trigger_type);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_messages_trigger_type;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_messages_meta_message_id;")
    op.execute("""
        ALTER TABLE whatsapp_messages 
        DROP COLUMN IF EXISTS retry_count,
        DROP COLUMN IF EXISTS error_message,
        DROP COLUMN IF EXISTS meta_message_id,
        DROP COLUMN IF EXISTS trigger_type,
        DROP COLUMN IF EXISTS status;
    """)
