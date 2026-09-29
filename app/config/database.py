import logging
import re
import time
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    Session,
    Mapper,
)

from app.config.settings import settings

logger = logging.getLogger("app.config.database")


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
    "pool_pre_ping": True,
    "pool_size": 3 if is_prod else 5,
    "max_overflow": 5 if is_prod else 10,
    "pool_timeout": 15,
    "pool_recycle": 300,  # Recicla conexões a cada 5 min para evitar que caiam por inatividade
}

if settings.DATABASE_URL.startswith("postgresql"):
    engine_args["connect_args"] = {
        "connect_timeout": 10,  # Evita travamento de 4 minutos no Linux se o pooler oscilar
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "client_encoding": "utf8",  # Evita erro "server didn't return client encoding" no handshake do pooler
    }

engine = create_engine(
    settings.DATABASE_URL,
    **engine_args
)


@event.listens_for(engine, "do_connect")
def provide_connection_with_retry(dialect, conn_rec, cargs, cparams):
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            return dialect.connect(*cargs, **cparams)
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    f"Falha transitória ao conectar no banco de dados (tentativa {attempt + 1}/{max_retries + 1}): {exc}. "
                    "Retentando em 0.5s..."
                )
                time.sleep(0.5)
                continue
            logger.error(
                f"Falha definitiva ao conectar no banco de dados após {max_retries + 1} tentativas: {exc}"
            )
            raise


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
