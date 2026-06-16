

from app.config.database import SessionLocal
from app.config.seeds import seed_plans, seed_tenant_types, seed_whatsapp_templates
from app.modules.models_loader import load_all_models


def run_seed():
    load_all_models()
    db = SessionLocal()
    try:
        seed_plans(db)
        seed_tenant_types(db)
        seed_whatsapp_templates(db)
        print("Required metadata seeded successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()