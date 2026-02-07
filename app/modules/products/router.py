from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)
from .service import ProductService

router = APIRouter(prefix="/products", tags=["Products"],dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=ProductResponse)
def create_product(
    data: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_product(db, tenant_id, data)


@router.get("/", response_model=list[ProductResponse])
def list_products(
    request: Request,
    db: Session = Depends(get_db),
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_products(db, tenant_id)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_product(
        db, tenant_id, product_id
    )


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_product(
        db, tenant_id, product_id, data
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_product(
        db, tenant_id, product_id
    )
