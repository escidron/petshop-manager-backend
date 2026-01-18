from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
)
from .service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("/", response_model=TenantResponse)
def create_tenant(
    data: TenantCreate,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.create_tenant(db, data)


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
