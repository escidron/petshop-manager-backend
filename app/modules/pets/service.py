import os
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from .repository import PetRepository
from .schemas import PetCreate, PetUpdate
from .models import PetPhoto



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

    def add_pet_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        file_content: bytes,
        filename: str,
        content_type: str,
        is_profile: bool,
        category: str,
    ):
        # 1. Garante que o pet existe e pertence ao tenant
        self.get_pet(db, tenant_id, pet_id)

        # 2. Gera um nome de arquivo único
        import uuid
        ext = os.path.splitext(filename)[1] or ".jpg"
        unique_filename = f"pets/{pet_id}/{uuid.uuid4()}{ext}"

        # 3. Faz upload no GCS
        from app.services.gcs_service import GCSService
        gcs = GCSService()
        photo_url = gcs.upload_file(file_content, unique_filename, content_type)

        # 4. Se for foto de perfil, desmarca as outras
        if is_profile:
            db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id, PetPhoto.tenant_id == tenant_id).update({"is_profile": False})

        # 5. Salva no banco de dados
        new_photo = PetPhoto(
            tenant_id=tenant_id,
            pet_id=pet_id,
            photo_url=photo_url,
            is_profile=is_profile,
            category=category
        )
        db.add(new_photo)
        db.commit()
        db.refresh(new_photo)
        return new_photo

    def delete_pet_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        photo_id: int,
    ):
        # Garante que o pet pertence ao tenant
        self.get_pet(db, tenant_id, pet_id)

        photo = db.query(PetPhoto).filter(
            PetPhoto.id == photo_id,
            PetPhoto.pet_id == pet_id,
            PetPhoto.tenant_id == tenant_id
        ).first()
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto não encontrada",
            )

        # Remove do GCS
        from app.services.gcs_service import GCSService
        gcs = GCSService()
        bucket_prefix = f"https://storage.googleapis.com/{gcs.bucket_name}/"
        if photo.photo_url.startswith(bucket_prefix):
            blob_name = photo.photo_url[len(bucket_prefix):]
            try:
                gcs.delete_file(blob_name)
            except Exception as e:
                # Loga o erro mas deleta do banco para não ficar órfão
                print(f"Erro ao deletar arquivo do GCS: {e}")

        db.delete(photo)
        db.commit()

    def set_profile_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        photo_id: int,
    ):
        self.get_pet(db, tenant_id, pet_id)

        photo = db.query(PetPhoto).filter(
            PetPhoto.id == photo_id,
            PetPhoto.pet_id == pet_id,
            PetPhoto.tenant_id == tenant_id
        ).first()
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto não encontrada",
            )

        db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id, PetPhoto.tenant_id == tenant_id).update({"is_profile": False})
        photo.is_profile = True
        db.commit()
        db.refresh(photo)
        return photo

