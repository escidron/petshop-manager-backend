from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import (
    PetCreate,
    PetUpdate,
    PetResponse,
)
from .service import PetService

router = APIRouter(prefix="/pets", tags=["Pets"])


@router.post("/", response_model=PetResponse)
def create_pet(
    tenant_id: int,
    data: PetCreate,
    db: Session = Depends(get_db),
):
    service = PetService()
    return service.create_pet(db, tenant_id, data)


@router.get(
    "/client/{client_id}",
    response_model=list[PetResponse],
)
def list_pets_by_client(
    tenant_id: int,
    client_id: int,
    db: Session = Depends(get_db),
):
    service = PetService()
    return service.list_pets_by_client(
        db, tenant_id, client_id
    )


@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(
    tenant_id: int,
    pet_id: int,
    db: Session = Depends(get_db),
):
    service = PetService()
    return service.get_pet(db, tenant_id, pet_id)


@router.patch("/{pet_id}", response_model=PetResponse)
def update_pet(
    tenant_id: int,
    pet_id: int,
    data: PetUpdate,
    db: Session = Depends(get_db),
):
    service = PetService()
    return service.update_pet(
        db, tenant_id, pet_id, data
    )


@router.delete("/{pet_id}", status_code=204)
def delete_pet(
    tenant_id: int,
    pet_id: int,
    db: Session = Depends(get_db),
):
    service = PetService()
    service.delete_pet(db, tenant_id, pet_id)
