from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
)
from .service import ServiceService

router = APIRouter(prefix="/services", tags=["Services"], dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=ServiceResponse, dependencies=[Depends(require_active_subscription)])
def create_service(
    data: ServiceCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().create(db, tenant_id, data)


@router.get("/", response_model=list[ServiceResponse])
def list_services(
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().list(db, tenant_id)


@router.patch("/{service_id}", response_model=ServiceResponse, dependencies=[Depends(require_active_subscription)])
def update_service(
    service_id: int,
    data: ServiceUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().update(db, tenant_id, service_id, data)


@router.delete("/{service_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_service(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    ServiceService().delete(db, tenant_id, service_id)
