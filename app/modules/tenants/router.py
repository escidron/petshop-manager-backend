from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.dependencies import require_owner

from .schemas import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantUserCreate,
    TenantUserResponse,
)
from app.modules.subscriptions.schemas import SubscriptionUpdate, SubscriptionResponse
from .service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("/users", response_model=list[TenantUserResponse])
def list_tenant_users(
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    return service.list_tenant_users(db, context["tenant"].id)


@router.post("/users", response_model=TenantUserResponse, status_code=201)
def create_tenant_user(
    data: TenantUserCreate,
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    return service.create_tenant_user(db, context["tenant"].id, data)


@router.delete("/users/{user_id}", status_code=204)
def remove_tenant_user(
    user_id: int,
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    service.remove_tenant_user(
        db,
        context["tenant"].id,
        user_id,
        context["user"].id,
    )


@router.post("/", response_model=TenantResponse)
def create_tenant(
    user_id: int,
    data: TenantCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    service = TenantService()
    result = service.create_tenant(db, data, user_id)

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=result["access_token"],
        httponly=True,
        secure=False,  # True em prod
        samesite="lax",
        path="/",
    )

    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=result["refresh_token"],
        httponly=True,
        secure=False,  # True em prod
        samesite="lax",
        path="/",
    )
    return result["tenant"]


@router.get("/", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)):
    service = TenantService()
    return service.list_tenants(db)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.get_tenant(db, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.update_tenant(db, tenant_id, data)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = TenantService()
    service.delete_tenant(db, tenant_id)


@router.patch("/{tenant_id}/subscription", response_model=SubscriptionResponse)
def update_subscription(
    tenant_id: int,
    data: SubscriptionUpdate,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.update_subscription(db, tenant_id, data)
