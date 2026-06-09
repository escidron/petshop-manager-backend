from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
)
from .service import ClientService

router = APIRouter(prefix="/clients", tags=["Clients"], dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=ClientResponse, dependencies=[Depends(require_active_subscription)])
def create_client(
    data: ClientCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_client(db, tenant_id, data)


@router.get("/", response_model=list[ClientResponse])
def list_clients(
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_clients(db, tenant_id)


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_client(db, tenant_id, client_id)


@router.patch("/{client_id}", response_model=ClientResponse, dependencies=[Depends(require_active_subscription)])
def update_client(
    client_id: int,
    data: ClientUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_client(db, tenant_id, client_id, data)


@router.delete("/{client_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_client(db, tenant_id, client_id)
