from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from app.modules.suppliers import schemas, service

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get("/", response_model=List[schemas.SupplierResponse])
def get_suppliers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    auth_data: dict = Depends(get_current_tenant),
):
    tenant_id = auth_data["tenant"].id
    return service.get_suppliers(db, tenant_id, skip=skip, limit=limit)


@router.get("/{supplier_id}", response_model=schemas.SupplierResponse)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    auth_data: dict = Depends(get_current_tenant),
):
    tenant_id = auth_data["tenant"].id
    return service.get_supplier(db, supplier_id, tenant_id)


@router.post("/", response_model=schemas.SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    supplier: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    auth_data: dict = Depends(require_active_subscription),
):
    tenant_id = auth_data["tenant"].id
    return service.create_supplier(db, supplier, tenant_id)


@router.put("/{supplier_id}", response_model=schemas.SupplierResponse)
def update_supplier(
    supplier_id: int,
    supplier: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
    auth_data: dict = Depends(require_active_subscription),
):
    tenant_id = auth_data["tenant"].id
    return service.update_supplier(db, supplier_id, supplier, tenant_id)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    auth_data: dict = Depends(require_active_subscription),
):
    tenant_id = auth_data["tenant"].id
    service.delete_supplier(db, supplier_id, tenant_id)
