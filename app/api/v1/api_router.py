from fastapi import APIRouter
from app.modules.users.router import router as users_router
from app.modules.clients.router import router as clients_router
from app.modules.tenants.router import router as tenants_router
from app.modules.pets.router import router as pets_router
from app.modules.products.router import router as products_router

api_router = APIRouter()

api_router.include_router(users_router)
api_router.include_router(clients_router)
api_router.include_router(tenants_router)
api_router.include_router(pets_router)
api_router.include_router(products_router)
