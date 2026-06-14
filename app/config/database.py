from typing import Generator
import re

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    Session,
    Mapper,
)

from app.config.settings import settings


# =========================
# Base ORM
# =========================
class Base(DeclarativeBase):
    pass


def clean_html(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    # Remove script and style blocks completely
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove other HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    return text.strip()


@event.listens_for(Mapper, "before_insert")
def sanitize_before_insert(mapper, connection, target):
    for attr in mapper.column_attrs:
        value = getattr(target, attr.key)
        if isinstance(value, str):
            setattr(target, attr.key, clean_html(value))


@event.listens_for(Mapper, "before_update")
def sanitize_before_update(mapper, connection, target):
    for attr in mapper.column_attrs:
        value = getattr(target, attr.key)
        if isinstance(value, str):
            setattr(target, attr.key, clean_html(value))



# =========================
# Engine
# =========================
is_prod = settings.ENVIRONMENT == "production"

engine_args = {
    "echo": settings.ENVIRONMENT == "development",
}

if is_prod:
    engine_args["poolclass"] = NullPool
else:
    engine_args.update({
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 600,
    })

engine = create_engine(
    settings.DATABASE_URL,
    **engine_args
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
