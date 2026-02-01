from sqlalchemy.orm import Session
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.pets.schemas import PetCreate, PetUpdate


class PetRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        data: PetCreate,
    ) -> Pet:
        pet = Pet(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(pet)
        db.commit()
        db.refresh(pet)
        return pet

    def get_by_id(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ) -> Pet | None:
        return (
            db.query(Pet)
            .filter(
                Pet.id == pet_id,
                Pet.tenant_id == tenant_id,
            )
            .first()
        )

    def list_pets(
        self, db: Session, tenant_id: int
    ) -> list[dict]:
        rows = (
            db.query(
                Pet.id.label("id"),
                Pet.name.label("name"),
                Pet.species.label("species"),
                Pet.breed.label("breed"),
                Pet.gender.label("gender"),
                Pet.age.label("age"),
                Pet.ageUnit.label("ageUnit"),
                Pet.client_id.label("client_id"),
                Client.name.label("owner_name"),
            )
            .join(Client, Client.id == Pet.client_id)
            .filter(Pet.tenant_id == tenant_id)
            .order_by(Pet.name)
            .all()
        )

        return [
            {
                "id": r.id,
                "name": r.name,
                "species": r.species,
                "breed": r.breed,
                "gender": r.gender,
                "age": r.age,
                "ageUnit": r.ageUnit,
                "client_id": r.client_id,
                "owner_name": r.owner_name,
            }
            for r in rows
        ]
    
    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ) -> list[Pet]:
        return (
            db.query(Pet)
            .filter(
                Pet.tenant_id == tenant_id,
                Pet.client_id == client_id,
            )
            .order_by(Pet.name)
            .all()
        )

    def update(
        self,
        db: Session,
        pet: Pet,
        data: PetUpdate,
    ) -> Pet:
        for field, value in data.model_dump(
            exclude_unset=True
        ).items():
            setattr(pet, field, value)

        db.commit()
        db.refresh(pet)
        return pet

    def delete(self, db: Session, pet: Pet):
        db.delete(pet)
        db.commit()
