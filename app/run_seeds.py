

from app.config.database import SessionLocal
from app.config.seeds import seed_plans


def run_seed():
    db = SessionLocal()
    try:
        seed_plans(db)
        print("Plans seeded successfully 🚀")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()