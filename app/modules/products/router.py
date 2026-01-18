from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)
from .service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/", response_model=ProductResponse)
def create_product(
    tenant_id: int,
    data: ProductCreate,
    db: Session = Depends(get_db),
):
    service = ProductService()
    return service.create_product(db, tenant_id, data)


@router.get("/", response_model=list[ProductResponse])
def list_products(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = ProductService()
    return service.list_products(db, tenant_id)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    tenant_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    service = ProductService()
    return service.get_product(
        db, tenant_id, product_id
    )


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    tenant_id: int,
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
):
    service = ProductService()
    return service.update_product(
        db, tenant_id, product_id, data
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    tenant_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    service = ProductService()
    service.delete_product(
        db, tenant_id, product_id
    )
