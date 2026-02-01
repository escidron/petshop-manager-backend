from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
)
from .service import ServiceService

router = APIRouter(prefix="/services", tags=["Services"])


@router.post("/", response_model=ServiceResponse)
def create_service(
    tenant_id: int,
    data: ServiceCreate,
    db: Session = Depends(get_db),
):
    return ServiceService().create(db, tenant_id, data)


@router.get("/", response_model=list[ServiceResponse])
def list_services(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    return ServiceService().list(db, tenant_id)


@router.patch("/{service_id}", response_model=ServiceResponse)
def update_service(
    tenant_id: int,
    service_id: int,
    data: ServiceUpdate,
    db: Session = Depends(get_db),
):
    return ServiceService().update(
        db, tenant_id, service_id, data
    )


@router.delete("/{service_id}", status_code=204)
def delete_service(
    tenant_id: int,
    service_id: int,
    db: Session = Depends(get_db),
):
    ServiceService().delete(
        db, tenant_id, service_id
    )
