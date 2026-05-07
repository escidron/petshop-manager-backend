from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.api.v1.api_router import api_router
from app.config.limiter import limiter
import app.modules.users.models
import app.modules.tenants.models
import app.modules.suppliers.models
import app.modules.products.models
import app.modules.sales.models
import app.modules.client_packages.models
import app.modules.appointments.models
import app.modules.subscriptions.models
import app.modules.plans.models

def create_app() -> FastAPI:
    from app.config.settings import settings

    app = FastAPI(title="Petshop API")
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
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(api_router, prefix="/api/v1")

    return app

app = create_app()
