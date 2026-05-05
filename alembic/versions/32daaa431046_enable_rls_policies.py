"""enable_rls_policies

Revision ID: 32daaa431046
Revises: 676b804b2b05
Create Date: 2026-05-02 12:13:58.413627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32daaa431046'
down_revision: Union[str, Sequence[str], None] = '676b804b2b05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable RLS on all multi-tenant tables
    tables_with_tenant_id = [
        "tenants", "tenant_users", "pets", "clients", "services", 
        "appointments", "suppliers", "products", "inventory_logs", 
        "sales", "packages", "employees", "subscriptions", 
        "client_packages", "commission_rules", "commission_entries"
    ]

    for table in tables_with_tenant_id:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        
        # Policy for the table
        if table == "tenants":
            op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (id = (current_setting('app.current_tenant_id', true)::integer));
            """)
        else:
            op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (tenant_id = (current_setting('app.current_tenant_id', true)::integer));
            """)

    # 2. Enable RLS and Create Join-based Policies for sub-tables
    sub_tables = [
        ("appointment_items", "appointments", "appointment_id"),
        ("appointment_item_services", "appointment_items", "appointment_item_id"),
        ("appointment_package_coverages", "appointment_items", "appointment_item_id"),
        ("sale_items", "sales", "sale_id"),
        ("package_items", "packages", "package_id"),
        ("client_package_credits", "client_packages", "client_package_id"),
    ]

    for table, parent, foreign_key in sub_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        
        # Recursive policy or join-based
        if table == "appointment_item_services":
             op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (EXISTS (
                    SELECT 1 FROM appointment_items ai
                    JOIN appointments a ON a.id = ai.appointment_id
                    WHERE ai.id = {table}.{foreign_key}
                    AND a.tenant_id = (current_setting('app.current_tenant_id', true)::integer)
                ));
            """)
        elif table == "appointment_package_coverages":
             op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (EXISTS (
                    SELECT 1 FROM appointment_items ai
                    JOIN appointments a ON a.id = ai.appointment_id
                    WHERE ai.id = {table}.{foreign_key}
                    AND a.tenant_id = (current_setting('app.current_tenant_id', true)::integer)
                ));
            """)
        else:
            op.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (EXISTS (
                    SELECT 1 FROM {parent} p
                    WHERE p.id = {table}.{foreign_key}
                    AND p.tenant_id = (current_setting('app.current_tenant_id', true)::integer)
                ));
            """)


def downgrade() -> None:
    all_tables = [
        "tenants", "tenant_users", "pets", "clients", "services", 
        "appointments", "suppliers", "products", "inventory_logs", 
        "sales", "packages", "employees", "subscriptions", 
        "client_packages", "commission_rules", "commission_entries",
        "appointment_items", "appointment_item_services",
        "appointment_package_coverages", "sale_items", "package_items", 
        "client_package_credits"
    ]

    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
