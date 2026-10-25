

from app.config.database import SessionLocal
from app.config.seeds import sync_all_seeds
from app.modules.models_loader import load_all_models


def run_seed():
    load_all_models()
    db = SessionLocal()
    try:
        sync_all_seeds(db)
        print("Required metadata seeded/synchronized successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()