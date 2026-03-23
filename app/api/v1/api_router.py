from fastapi import APIRouter
from app.modules.users.router import router as users_router
from app.modules.clients.router import router as clients_router
from app.modules.tenants.router import router as tenants_router
from app.modules.pets.router import router as pets_router
from app.modules.products.router import router as products_router
from app.modules.tenant_services.router import router as tenant_services_router
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.address.router import router as address_router
from app.modules.onboarding.router import router as onboarding_router
from app.modules.packages.router import router as packages_router
from app.modules.sales.router import router as sales_router
from app.modules.client_packages.router import router as client_packages_router

api_router = APIRouter()

api_router.include_router(users_router)
api_router.include_router(clients_router)
api_router.include_router(tenants_router)
api_router.include_router(pets_router)
api_router.include_router(products_router)
api_router.include_router(tenant_services_router)
api_router.include_router(appointments_router)
api_router.include_router(auth_router)
api_router.include_router(address_router)
api_router.include_router(onboarding_router)
api_router.include_router(packages_router)
api_router.include_router(sales_router)
api_router.include_router(client_packages_router)
