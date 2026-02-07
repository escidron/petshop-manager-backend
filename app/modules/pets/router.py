from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import (
    PetCreate,
    PetUpdate,
    PetResponse,
)
from .service import PetService

router = APIRouter(prefix="/pets", tags=["Pets"],dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=PetResponse)
def create_pet(
    data: PetCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_pet(db, tenant_id, data)

@router.get(
    "/",
    response_model=list[PetResponse],
)
def list_pets(
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_pets(db, tenant_id)

@router.get(
    "/client/{client_id}",
    response_model=list[PetResponse],
)
def list_pets_by_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_pets_by_client(
        db, tenant_id, client_id
    )


@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_pet(db, tenant_id, pet_id)


@router.patch("/{pet_id}", response_model=PetResponse)
def update_pet(
    pet_id: int,
    data: PetUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_pet(
        db, tenant_id, pet_id, data
    )


@router.delete("/{pet_id}", status_code=204)
def delete_pet(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_pet(db, tenant_id, pet_id)
