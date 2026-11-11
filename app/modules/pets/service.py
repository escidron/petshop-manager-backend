import os
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.appointments.models import (
    Appointment,
    AppointmentAuditLog,
    AppointmentItem,
    AppointmentStatus,
)
from app.modules.clients.repository import ClientRepository
from app.modules.daycare.models import DaycareStay, DaycareStayStatus
from app.modules.waiting_list.models import (
    WaitingListEntry,
    WaitingListItem,
    WaitingListStatus,
)
from app.services.gcs_service import GCSService
from .models import Pet, PetPhoto
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

        pet = self.repository.create(db, tenant_id, data)
        if pet.is_deceased:
            self._handle_deceased_pet_schedules(db, tenant_id, pet)
        return pet

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
        include_photos: bool = True,
    ):
        pets = self.repository.list_by_client(
            db, tenant_id, client_id, include_photos=include_photos
        )
        if not include_photos:
            for pet in pets:
                pet.__dict__["photos"] = []
        return pets

    def update_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        data: PetUpdate,
    ):
        pet = self.get_pet(db, tenant_id, pet_id)
        updated_pet = self.repository.update(db, pet, data)
        if updated_pet.is_deceased:
            self._handle_deceased_pet_schedules(db, tenant_id, updated_pet)
        return updated_pet

    def _handle_deceased_pet_schedules(
        self,
        db: Session,
        tenant_id: int,
        pet: Pet,
    ) -> None:
        """
        Quando um pet é marcado como óbito (is_deceased=True):
        - Em agendamentos abertos (PENDING / CONFIRMED) de Banho & Tosa (incluindo recorrências):
          - Se o agendamento possui outros pets ativos, remove apenas este pet do agendamento e registra observação.
          - Se o agendamento era apenas deste pet (ou restaram apenas pets em óbito), cancela o agendamento e registra observação.
        - Em estadias futuras/pendentes da Creche (PENDING), cancela a estadia e registra observação.
        - Na Lista de Espera (PENDING), remove o pet se houver outros ou cancela a entrada se for único.
        """
        open_appointments = (
            db.query(Appointment)
            .options(selectinload(Appointment.items).joinedload(AppointmentItem.pet))
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.items.any(AppointmentItem.pet_id == pet.id),
            )
            .all()
        )

        for appt in open_appointments:
            deceased_items = [it for it in list(appt.items) if it.pet_id == pet.id]
            remaining_items = [
                it
                for it in list(appt.items)
                if it.pet_id != pet.id and not (it.pet and getattr(it.pet, "is_deceased", False))
            ]

            if len(remaining_items) == 0:
                appt.status = AppointmentStatus.CANCELED
                cancel_note = f"[Cancelado automaticamente: pet {pet.name} foi a óbito]"
                current_notes = (appt.notes or "").strip()
                if cancel_note not in current_notes:
                    appt.notes = f"{current_notes}\n{cancel_note}".strip() if current_notes else cancel_note

                db.add(
                    AppointmentAuditLog(
                        tenant_id=tenant_id,
                        appointment_id=appt.id,
                        pet_id=pet.id,
                        pet_name=pet.name,
                        action="appointment_canceled_deceased",
                        notes=f"Agendamento cancelado automaticamente devido ao óbito do pet '{pet.name}'",
                    )
                )
            else:
                deceased_item_ids = [it.id for it in deceased_items if it.id is not None]
                if deceased_item_ids:
                    db.query(AppointmentItem).filter(
                        AppointmentItem.id.in_(deceased_item_ids)
                    ).delete(synchronize_session=False)
                db.expire(appt, ["items"])

                removed_note = f"[Pet {pet.name} removido automaticamente do agendamento (óbito)]"
                current_notes = (appt.notes or "").strip()
                if removed_note not in current_notes:
                    appt.notes = f"{current_notes}\n{removed_note}".strip() if current_notes else removed_note

                db.add(
                    AppointmentAuditLog(
                        tenant_id=tenant_id,
                        appointment_id=appt.id,
                        pet_id=pet.id,
                        pet_name=pet.name,
                        action="pet_removed_deceased",
                        notes=f"Pet '{pet.name}' removido automaticamente do agendamento devido a óbito",
                    )
                )

            db.add(appt)

        open_stays = (
            db.query(DaycareStay)
            .filter(
                DaycareStay.tenant_id == tenant_id,
                DaycareStay.pet_id == pet.id,
                DaycareStay.status == DaycareStayStatus.PENDING.value,
            )
            .all()
        )
        for stay in open_stays:
            stay.status = DaycareStayStatus.CANCELED.value
            cancel_note = f"[Cancelado automaticamente: pet {pet.name} foi a óbito]"
            current_notes = (stay.notes or "").strip()
            if cancel_note not in current_notes:
                stay.notes = f"{current_notes}\n{cancel_note}".strip() if current_notes else cancel_note
            db.add(stay)

        open_wl_entries = (
            db.query(WaitingListEntry)
            .options(selectinload(WaitingListEntry.items).joinedload(WaitingListItem.pet))
            .filter(
                WaitingListEntry.tenant_id == tenant_id,
                WaitingListEntry.status == WaitingListStatus.PENDING,
                WaitingListEntry.items.any(WaitingListItem.pet_id == pet.id),
            )
            .all()
        )
        for entry in open_wl_entries:
            deceased_wl_items = [it for it in list(entry.items) if it.pet_id == pet.id]
            remaining_wl_items = [
                it
                for it in list(entry.items)
                if it.pet_id != pet.id and not (it.pet and getattr(it.pet, "is_deceased", False))
            ]
            if len(remaining_wl_items) == 0:
                entry.status = WaitingListStatus.CANCELED
                cancel_note = f"[Cancelado automaticamente: pet {pet.name} foi a óbito]"
                current_notes = (entry.notes or "").strip()
                if cancel_note not in current_notes:
                    entry.notes = (f"{current_notes}\n{cancel_note}".strip() if current_notes else cancel_note)[:500]
            else:
                deceased_wl_ids = [it.id for it in deceased_wl_items if it.id is not None]
                if deceased_wl_ids:
                    db.query(WaitingListItem).filter(
                        WaitingListItem.id.in_(deceased_wl_ids)
                    ).delete(synchronize_session=False)
                db.expire(entry, ["items"])
                removed_note = f"[Pet {pet.name} removido da lista de espera (óbito)]"
                current_notes = (entry.notes or "").strip()
                if removed_note not in current_notes:
                    entry.notes = (f"{current_notes}\n{removed_note}".strip() if current_notes else removed_note)[:500]
            db.add(entry)

        db.commit()
        db.refresh(pet)

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
        ext = os.path.splitext(filename)[1] or ".jpg"
        unique_filename = f"pets/{pet_id}/{uuid.uuid4()}{ext}"

        # 3. Faz upload no GCS
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

