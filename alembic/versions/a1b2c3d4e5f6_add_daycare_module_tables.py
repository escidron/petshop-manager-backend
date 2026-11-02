"""add_daycare_module_tables

Revision ID: a1b2c3d4e5f6
Revises: 8f2a1b3c4d5e
Create Date: 2026-10-31 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1c2b3a4f5e6'
down_revision: Union[str, Sequence[str], None] = '8f2a1b3c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS daycare_modalities (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            billing_type VARCHAR(20) NOT NULL DEFAULT 'daily',
            description VARCHAR(255),
            max_hours INTEGER,
            sizes JSON,
            price_cents INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        );
    """)
    op.execute("ALTER TABLE daycare_modalities ADD COLUMN IF NOT EXISTS sizes JSON;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_modalities_tenant_id ON daycare_modalities (tenant_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS daycare_stays (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
            modality_id INTEGER REFERENCES daycare_modalities(id) ON DELETE SET NULL,
            service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
            stay_type VARCHAR(20) NOT NULL DEFAULT 'daily',
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price_cents INTEGER NOT NULL DEFAULT 0,
            total_price_cents INTEGER NOT NULL DEFAULT 0,
            scheduled_start_at TIMESTAMP WITH TIME ZONE NOT NULL,
            scheduled_end_at TIMESTAMP WITH TIME ZONE NOT NULL,
            check_in_at TIMESTAMP WITH TIME ZONE,
            check_out_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            food_info VARCHAR(255),
            belongings VARCHAR(255),
            notes TEXT,
            client_package_credit_id INTEGER REFERENCES client_package_credits(id) ON DELETE SET NULL,
            covered_quantity INTEGER NOT NULL DEFAULT 0,
            sale_id INTEGER REFERENCES sales(id) ON DELETE SET NULL,
            comanda_id INTEGER REFERENCES comandas(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        );
    """)
    op.execute("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS modality_id INTEGER REFERENCES daycare_modalities(id) ON DELETE SET NULL;")
    op.execute("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS unit_price_cents INTEGER NOT NULL DEFAULT 0;")
    op.execute("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS total_price_cents INTEGER NOT NULL DEFAULT 0;")

    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_tenant_id ON daycare_stays (tenant_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_client_id ON daycare_stays (client_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_pet_id ON daycare_stays (pet_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_modality_id ON daycare_stays (modality_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_service_id ON daycare_stays (service_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_status ON daycare_stays (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_scheduled_start_at ON daycare_stays (scheduled_start_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_scheduled_end_at ON daycare_stays (scheduled_end_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_stays_tenant_dates ON daycare_stays (tenant_id, scheduled_start_at, scheduled_end_at);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS daycare_tasks (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            stay_id INTEGER NOT NULL REFERENCES daycare_stays(id) ON DELETE CASCADE,
            task_type VARCHAR(20) NOT NULL DEFAULT 'feeding',
            scheduled_time VARCHAR(5) NOT NULL,
            title VARCHAR(200) NOT NULL,
            notes VARCHAR(255),
            is_completed BOOLEAN NOT NULL DEFAULT FALSE,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_tasks_tenant_id ON daycare_tasks (tenant_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daycare_tasks_stay_id ON daycare_tasks (stay_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS pet_health_records (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
            category VARCHAR(30) NOT NULL DEFAULT 'vaccine',
            name VARCHAR(150) NOT NULL,
            applied_at DATE NOT NULL,
            expires_at DATE,
            notes VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pet_health_records_tenant_id ON pet_health_records (tenant_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pet_health_records_pet_id ON pet_health_records (pet_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pet_health_records_expires_at ON pet_health_records (expires_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pet_health_records;")
    op.execute("DROP TABLE IF EXISTS daycare_tasks;")
    op.execute("DROP TABLE IF EXISTS daycare_stays;")
    op.execute("DROP TABLE IF EXISTS daycare_modalities;")
