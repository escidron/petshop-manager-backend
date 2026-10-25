import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.api.v1.api_router import api_router
from app.config.limiter import limiter
from app.config.logging_config import setup_logging
from app.config.observability_middleware import ObservabilityMiddleware
import app.modules.users.models
import app.modules.tenants.models
import app.modules.suppliers.models
import app.modules.products.models
import app.modules.sales.models
import app.modules.client_packages.models
import app.modules.appointments.models
import app.modules.subscriptions.models
import app.modules.plans.models
import app.modules.auth.models
import app.modules.waiting_list.models
import app.modules.whatsapp.models
import app.modules.cash_register.models
import app.modules.financial.models
import sentry_sdk
from app.config.database import SessionLocal
from app.config.seeds import sync_all_seeds
from app.config.settings import settings
from sqlalchemy import text
from app.config.database import SessionLocal

logger = logging.getLogger(__name__)


# Initialize Logging Configuration
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executado na inicialização do servidor em todos os ambientes (Dev, Staging, Prod).
    Garante que novos planos, add-ons e metadados sejam sempre sincronizados automaticamente
    com o banco de dados no momento do deploy/boot.
    """
    try:
        db = SessionLocal()
        try:
            sync_all_seeds(db)
            logger.info("Metadados e catálogo de planos sincronizados com sucesso no boot.")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"Erro ao sincronizar sementes no boot da aplicação: {exc}", exc_info=True)

    yield


def create_app() -> FastAPI:

    app = FastAPI(title="Petshop API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ObservabilityMiddleware)

    app.include_router(api_router, prefix="/api/v1")

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.0,
            send_default_pii=True
        )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.get("/health/db-quota")
    def db_quota_check():

        session = SessionLocal()
        try:
            size_bytes = session.execute(text("SELECT pg_database_size(current_database());")).scalar() or 0
            size_mb = round(size_bytes / (1024 * 1024), 2)
            quota_mb = 500.0
            percent_used = round((size_mb / quota_mb) * 100, 1)

            if percent_used >= 85:
                sentry_sdk.capture_message(
                    f"URGENTE: Banco de dados com {size_mb} MB ({percent_used}% da cota de {quota_mb} MB). Risco iminente de limite atingido! Faça upgrade para o plano Pro imediatamente.",
                    level="error",
                )
            elif percent_used >= 70:
                sentry_sdk.capture_message(
                    f"AVISO DE COTA: Banco de dados com {size_mb} MB ({percent_used}% da cota de {quota_mb} MB). Planeje upgrade ou limpeza de dados.",
                    level="warning",
                )

            return {
                "status": "warning" if percent_used >= 70 else "ok",
                "database_size_mb": size_mb,
                "free_quota_mb": quota_mb,
                "percent_used": percent_used,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
        finally:
            session.close()

    return app

app = create_app()
