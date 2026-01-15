from fastapi import FastAPI
from app.api.v1.api_router import api_router
import app.modules.users.models

def create_app() -> FastAPI:
    app = FastAPI(title="Petshop API")

    app.include_router(api_router, prefix="/api/v1")

    return app

app = create_app()