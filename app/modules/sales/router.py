from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import SaleCreate, SaleResponse
from .service import SalesService

router = APIRouter(prefix="/sales", tags=["PDV / Vendas"], dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=SaleResponse)
def create_sale(data: SaleCreate, request: Request, db: Session = Depends(get_db)):
    service = SalesService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_sale(db, tenant_id, data)


@router.get("/", response_model=List[SaleResponse])
def list_sales(skip: int = 0, limit: int = 100, request: Request = None, db: Session = Depends(get_db)):
    service = SalesService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_sales(db, tenant_id, skip, limit)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: int, request: Request, db: Session = Depends(get_db)):
    service = SalesService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_sale(db, tenant_id, sale_id)


@router.post("/{sale_id}/cancel", response_model=SaleResponse)
def cancel_sale(sale_id: int, request: Request, db: Session = Depends(get_db)):
    service = SalesService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.cancel_sale(db, tenant_id, sale_id)
