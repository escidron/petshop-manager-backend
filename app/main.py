from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api_router import api_router
import app.modules.users.models
import app.modules.tenants.models
import app.modules.products.models
import app.modules.sales.models

def create_app() -> FastAPI:
    from app.config.settings import settings

    app = FastAPI(title="Petshop API")

    origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    return app

app = create_app()
