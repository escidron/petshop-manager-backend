from sqlalchemy import func, and_, or_, distinct
from sqlalchemy.orm import Session, joinedload

from app.modules.appointments.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemService,
    AppointmentStatus,
)
from app.modules.clients.models import Client
from app.modules.pets.models import Pet, PetPhoto
from app.modules.pets.schemas import PetCreate, PetUpdate
from app.modules.tenant_services.models import Service


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
            .options(joinedload(Pet.photos))
            .filter(
                Pet.id == pet_id,
                Pet.tenant_id == tenant_id,
            )
            .first()
        )

    def list_pets(self, db: Session, tenant_id: int) -> list[Pet]:
        return (
            db.query(Pet)
            .options(joinedload(Pet.client), joinedload(Pet.photos))
            .filter(Pet.tenant_id == tenant_id)
            .order_by(Pet.name)
            .all()
        )
    
    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        include_photos: bool = True,
    ) -> list[Pet]:
        q = db.query(Pet).filter(
            Pet.tenant_id == tenant_id,
            Pet.client_id == client_id,
        )
        if include_photos:
            q = q.options(joinedload(Pet.photos))
        return q.order_by(Pet.name).all()

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

    def get_clients_pets_query(
        self,
        db: Session,
        tenant_id: int,
        is_active: bool | None = None,
        search: str | None = None,
    ):
        query = (
            db.query(Pet)
            .join(Client, Client.id == Pet.client_id)
            .options(joinedload(Pet.client))
            .filter(Pet.tenant_id == tenant_id)
        )

        if is_active is not None:
            query = query.filter(Pet.is_active == is_active)

        if search:
            s = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Pet.name.ilike(s),
                    Client.name.ilike(s),
                    Client.phone.ilike(s),
                    Pet.breed.ilike(s),
                )
            )

        return query.order_by(Client.name.asc(), Pet.name.asc())

    def get_report_counts(
        self,
        db: Session,
        tenant_id: int,
    ) -> tuple[int, int]:
        """Retorna (total_active_pets, total_unique_clients) para o tenant."""
        total_active_pets = (
            db.query(func.count(Pet.id))
            .filter(Pet.tenant_id == tenant_id, Pet.is_active == True)
            .scalar()
            or 0
        )
        total_unique_clients = (
            db.query(func.count(distinct(Pet.client_id)))
            .filter(Pet.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        return total_active_pets, total_unique_clients

    def get_last_services_map(
        self,
        db: Session,
        tenant_id: int,
        pet_ids: list[int],
    ) -> dict[int, dict]:
        """
        Retorna dicionário pet_id -> {"scheduled_at": datetime, "service_name": str}
        para os últimos agendamentos não-cancelados dos pets informados.
        """
        if not pet_ids:
            return {}

        # 1. Busca primeiro o agendamento mais recente no passado ou concluído
        latest_past_subq = (
            db.query(
                AppointmentItem.pet_id,
                func.max(Appointment.scheduled_at).label("max_scheduled_at"),
            )
            .join(Appointment, Appointment.id == AppointmentItem.appointment_id)
            .filter(
                Appointment.tenant_id == tenant_id,
                AppointmentItem.pet_id.in_(pet_ids),
                Appointment.status.notin_([AppointmentStatus.CANCELED, AppointmentStatus.NO_SHOW]),
                or_(
                    Appointment.scheduled_at <= func.now(),
                    Appointment.status == AppointmentStatus.COMPLETED,
                ),
            )
            .group_by(AppointmentItem.pet_id)
            .subquery()
        )

        latest_items = (
            db.query(
                AppointmentItem.pet_id,
                Appointment.scheduled_at,
                AppointmentItem.id.label("item_id"),
            )
            .join(Appointment, Appointment.id == AppointmentItem.appointment_id)
            .join(
                latest_past_subq,
                and_(
                    AppointmentItem.pet_id == latest_past_subq.c.pet_id,
                    Appointment.scheduled_at == latest_past_subq.c.max_scheduled_at,
                ),
            )
            .filter(Appointment.tenant_id == tenant_id)
            .all()
        )

        # 2. Para pets sem atendimento passado, busca o próximo agendamento futuro mais próximo
        found_pet_ids = {row.pet_id for row in latest_items}
        remaining_pet_ids = [pid for pid in pet_ids if pid not in found_pet_ids]
        if remaining_pet_ids:
            future_subq = (
                db.query(
                    AppointmentItem.pet_id,
                    func.min(Appointment.scheduled_at).label("min_scheduled_at"),
                )
                .join(Appointment, Appointment.id == AppointmentItem.appointment_id)
                .filter(
                    Appointment.tenant_id == tenant_id,
                    AppointmentItem.pet_id.in_(remaining_pet_ids),
                    Appointment.status.notin_([AppointmentStatus.CANCELED, AppointmentStatus.NO_SHOW]),
                    Appointment.scheduled_at > func.now(),
                )
                .group_by(AppointmentItem.pet_id)
                .subquery()
            )

            future_items = (
                db.query(
                    AppointmentItem.pet_id,
                    Appointment.scheduled_at,
                    AppointmentItem.id.label("item_id"),
                )
                .join(Appointment, Appointment.id == AppointmentItem.appointment_id)
                .join(
                    future_subq,
                    and_(
                        AppointmentItem.pet_id == future_subq.c.pet_id,
                        Appointment.scheduled_at == future_subq.c.min_scheduled_at,
                    ),
                )
                .filter(Appointment.tenant_id == tenant_id)
                .all()
            )
            latest_items.extend(future_items)

        if not latest_items:
            return {}

        item_id_to_pet: dict[int, int] = {}
        item_to_scheduled: dict[int, object] = {}
        for row in latest_items:
            item_id_to_pet[row.item_id] = row.pet_id
            item_to_scheduled[row.item_id] = row.scheduled_at

        item_ids = list(item_id_to_pet.keys())

        services_rows = (
            db.query(
                AppointmentItemService.appointment_item_id,
                Service.name,
            )
            .join(Service, Service.id == AppointmentItemService.service_id)
            .filter(
                AppointmentItemService.appointment_item_id.in_(item_ids),
                AppointmentItemService.status == "active",
            )
            .all()
        )

        services_by_item: dict[int, list[str]] = {}
        for item_id, s_name in services_rows:
            services_by_item.setdefault(item_id, []).append(s_name)

        result: dict[int, dict] = {}
        for item_id, pet_id in item_id_to_pet.items():
            s_list = services_by_item.get(item_id, [])
            s_name = ", ".join(s_list) if s_list else "Serviço"
            if pet_id not in result or item_to_scheduled[item_id] >= result[pet_id]["scheduled_at"]:
                result[pet_id] = {
                    "scheduled_at": item_to_scheduled[item_id],
                    "service_name": s_name,
                }

        return result
