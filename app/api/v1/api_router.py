from fastapi import APIRouter
from app.modules.users.router import router as users_router
from app.modules.clients.router import router as clients_router
from app.modules.tenants.router import router as tenants_router

api_router = APIRouter()

api_router.include_router(users_router)
api_router.include_router(clients_router)
api_router.include_router(tenants_router)
