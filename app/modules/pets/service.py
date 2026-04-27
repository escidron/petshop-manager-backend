from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from .repository import PetRepository
from .schemas import PetCreate, PetUpdate


class PetService:
    def __init__(self):
        self.repository = PetRepository()
        self.client_repository = ClientRepository()

    def create_pet(
        self,
        db: Session,
        tenant_id: int,
        data: PetCreate,
    ):
        client = self.client_repository.get_by_id(
            db, tenant_id, data.client_id
        )
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente não encontrado",
            )

        return self.repository.create(db, tenant_id, data)

    def get_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ):
        pet = self.repository.get_by_id(
            db, tenant_id, pet_id
        )
        if not pet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pet não encontrado",
            )
        return pet

    def list_pets(self, db: Session, tenant_id: int):
        return self.repository.list_pets(db, tenant_id)
    
    def list_pets_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ):
        return self.repository.list_by_client(
            db, tenant_id, client_id
        )

    def update_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        data: PetUpdate,
    ):
        pet = self.get_pet(db, tenant_id, pet_id)
        return self.repository.update(db, pet, data)

    def delete_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ):
        pet = self.get_pet(db, tenant_id, pet_id)
        self.repository.delete(db, pet)
