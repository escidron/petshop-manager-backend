"""add_whatsapp_retry_dedup_and_refund

Revision ID: 8f2a1b3c4d5e
Revises: 687d791cc20b
Create Date: 2026-10-26 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2a1b3c4d5e'
down_revision: Union[str, Sequence[str], None] = '687d791cc20b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE whatsapp_messages 
        ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS error_code VARCHAR(50),
        ADD COLUMN IF NOT EXISTS refunded BOOLEAN DEFAULT FALSE NOT NULL;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_whatsapp_messages_next_retry_at ON whatsapp_messages (next_retry_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_whatsapp_messages_status ON whatsapp_messages (status);")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_messages_appt_trigger 
        ON whatsapp_messages (appointment_id, trigger_type) 
        WHERE direction = 'outbound' AND trigger_type IS NOT NULL AND trigger_type != 'reply';
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_whatsapp_messages_appt_trigger;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_messages_status;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_messages_next_retry_at;")
    op.execute("""
        ALTER TABLE whatsapp_messages 
        DROP COLUMN IF EXISTS refunded,
        DROP COLUMN IF EXISTS error_code,
        DROP COLUMN IF EXISTS next_retry_at;
    """)
