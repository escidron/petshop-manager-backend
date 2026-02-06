from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
)
from .service import ClientService

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("/",response_model=ClientResponse)
def create_client(
    tenant_id: int,
    data: ClientCreate,
    db: Session = Depends(get_db),
):
    service = ClientService()
    return service.create_client(db, tenant_id, data)


@router.get(
    "/",
    response_model=list[ClientResponse],
)
def list_clients(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = ClientService()
    return service.list_clients(db, tenant_id)


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
)
def get_client(
    tenant_id: int,
    client_id: int,
    db: Session = Depends(get_db),
):
    service = ClientService()
    return service.get_client(db, tenant_id, client_id)


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
)
def update_client(
    tenant_id: int,
    client_id: int,
    data: ClientUpdate,
    db: Session = Depends(get_db),
):
    service = ClientService()
    return service.update_client(
        db, tenant_id, client_id, data
    )


@router.delete(
    "/{client_id}",
    status_code=204,
)
def delete_client(
    tenant_id: int,
    client_id: int,
    db: Session = Depends(get_db),
):
    service = ClientService()
    service.delete_client(db, tenant_id, client_id)
