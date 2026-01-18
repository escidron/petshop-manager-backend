from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    ClienteCreate,
    ClienteUpdate,
    ClienteResponse,
)
from .service import ClienteService

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post(
    "/",
    response_model=ClienteResponse,
)
def create_cliente(
    tenant_id: int,
    data: ClienteCreate,
    db: Session = Depends(get_db),
):
    service = ClienteService()
    return service.create_cliente(db, tenant_id, data)


@router.get(
    "/",
    response_model=list[ClienteResponse],
)
def list_clientes(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = ClienteService()
    return service.list_clientes(db, tenant_id)


@router.get(
    "/{cliente_id}",
    response_model=ClienteResponse,
)
def get_cliente(
    tenant_id: int,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    service = ClienteService()
    return service.get_cliente(db, tenant_id, cliente_id)


@router.patch(
    "/{cliente_id}",
    response_model=ClienteResponse,
)
def update_cliente(
    tenant_id: int,
    cliente_id: int,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
):
    service = ClienteService()
    return service.update_cliente(
        db, tenant_id, cliente_id, data
    )


@router.delete(
    "/{cliente_id}",
    status_code=204,
)
def delete_cliente(
    tenant_id: int,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    service = ClienteService()
    service.delete_cliente(db, tenant_id, cliente_id)
