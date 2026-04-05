

from app.config.database import SessionLocal
from app.config.seeds import seed_plans, seed_tenant_types


def run_seed():
    db = SessionLocal()
    try:
        seed_plans(db)
        seed_tenant_types(db)
        print("Required metadata seeded successfully 🚀.")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()