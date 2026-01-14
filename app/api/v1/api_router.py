from fastapi import APIRouter
from app.modules.pets.router import router as pets_router

api_router = APIRouter()

api_router.include_router(pets_router)