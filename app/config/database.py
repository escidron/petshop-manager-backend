from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    Session,
)

from app.config.settings import settings


# =========================
# Base ORM
# =========================
class Base(DeclarativeBase):
    pass


# =========================
# Engine
# =========================
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=600,   # recicla conexões a cada 10 min (importante para Supabase)
    echo=settings.ENVIRONMENT == "development",
)


# =========================
# Session
# =========================
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# =========================
# Dependency (FastAPI)
# =========================
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
