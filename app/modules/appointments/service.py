from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments.models import AppointmentAction, AppointmentStatus

from .repository import AppointmentRepository
from .schemas import AppointmentCreate, AppointmentUpdate
from app.modules.pets.models import Pet
from app.modules.clients.models import Client
from app.modules.tenant_services.models import Service


class AppointmentService:
    def __init__(self):
        self.repo = AppointmentRepository()
    
    TRANSITIONS = {
        AppointmentStatus.PENDING: {
            AppointmentAction.CONFIRM: AppointmentStatus.CONFIRMED,
            AppointmentAction.CANCEL: AppointmentStatus.CANCELED,
            AppointmentAction.NO_SHOW: AppointmentStatus.NO_SHOW,
        },
        AppointmentStatus.CONFIRMED: {
            AppointmentAction.START: AppointmentStatus.IN_PROGRESS,
            AppointmentAction.CANCEL: AppointmentStatus.CANCELED,
            AppointmentAction.NO_SHOW: AppointmentStatus.NO_SHOW,
        },
        AppointmentStatus.IN_PROGRESS: {
            AppointmentAction.COMPLETE: AppointmentStatus.COMPLETED,
        },
    }
    # ---------- CREATE ----------
    def create(
        self,
        db: Session,
        tenant_id: int,
        data: AppointmentCreate,
    ):
        self._validate_client_and_pet(db, tenant_id, data.client_id, data.pet_id)
        services = self._get_services(db, tenant_id, data.service_ids)

        return self.repo.create(
            db,
            tenant_id,
            data.client_id,
            data.pet_id,
            data.scheduled_at,
            services,
            data.notes,
        )

    # ---------- GET ----------
    def get(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
    ):
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)
        if not appointment:
            raise HTTPException(404, "Appointment not found")
        return appointment

    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ):
        return self.repo.list_by_day(db, tenant_id, day)

    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ):
        return self.repo.list_by_client(db, tenant_id, client_id)

    # ---------- UPDATE ----------
    def update(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        data: AppointmentUpdate,
    ):
        appointment = self.get(db, tenant_id, appointment_id)

        services = None
        if data.service_ids is not None:
            services = self._get_services(
                db, tenant_id, data.service_ids
            )

        return self.repo.update(
            db,
            appointment,
            scheduled_at=data.scheduled_at,
            services=services,
        )

    # ---------- DELETE ----------
    def delete(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
    ):
        appointment = self.get(db, tenant_id, appointment_id)
        self.repo.delete(db, appointment)

    # ---------- helpers ----------
    def _validate_client_and_pet(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
    ):
        client = (
            db.query(Client)
            .filter(
                Client.id == client_id,
                Client.tenant_id == tenant_id,
            )
            .first()
        )
        if not client:
            raise HTTPException(404, "Client not found")

        pet = (
            db.query(Pet)
            .filter(
                Pet.id == pet_id,
                Pet.client_id == client_id,
                Pet.tenant_id == tenant_id,
            )
            .first()
        )
        if not pet:
            raise HTTPException(404, "Pet not found")

    def _get_services(
        self,
        db: Session,
        tenant_id: int,
        service_ids: list[int],
    ) -> list[Service]:
        services = (
            db.query(Service)
            .filter(
                Service.id.in_(service_ids),
                Service.tenant_id == tenant_id,
                Service.is_active,
            )
            .all()
        )

        if len(services) != len(service_ids):
            raise HTTPException(
                400, "One or more services are invalid"
            )

        return services
    
    def apply_action(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        action: AppointmentAction,
    ):
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)

        if not appointment:
            return ("Agendamento não encontrado")

        current_status = appointment.status

        if current_status not in self.TRANSITIONS:
            raise HTTPException(
                status_code=400,
                detail="Ação inválida para o status atual",
            )

        if action not in self.TRANSITIONS[current_status]:
            raise HTTPException(
                status_code=400,
                detail=f"Ação '{action}' inválida para status '{current_status}'",
            )

        new_status = self.TRANSITIONS[current_status][action]
        appointment.status = new_status

        return self.repo.save_action(db, appointment)
