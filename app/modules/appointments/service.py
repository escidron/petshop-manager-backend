from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments.models import AppointmentAction, AppointmentStatus

from .repository import AppointmentRepository
from .schemas import AppointmentCreate, AppointmentUpdate
from app.modules.pets.models import Pet
from app.modules.clients.models import Client
from app.modules.tenant_services.models import Service
from app.modules.client_packages.repository import ClientPackageRepository
from app.modules.tenants.models import Tenant


class AppointmentService:
    def __init__(self):
        self.repo = AppointmentRepository()
        self.credit_repo = ClientPackageRepository()
    
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
        # 1️⃣ Validar cliente primeiro (uma única vez)
        client = (
            db.query(Client)
            .filter(
                Client.id == data.client_id,
                Client.tenant_id == tenant_id,
            )
            .first()
        )
        if not client:
            raise HTTPException(404, "Client not found")

        # 2️⃣ Criar appointment root
        appointment = self.repo.create(
            db=db,
            tenant_id=tenant_id,
            client_id=data.client_id,
            scheduled_at=data.scheduled_at,
            notes=data.notes,
        )

        # 3️⃣ Para cada pet no payload
        for item in data.items:

            # Aqui reaproveitamos sua validação
            self._validate_pet(
                db,
                tenant_id,
                data.client_id,
                item.pet_id,
            )

            services = self._get_services(
                db,
                tenant_id,
                item.service_ids,
            )

            self.repo.create_item(
                db=db,
                appointment=appointment,
                pet_id=item.pet_id,
                services=services,
            )

        # Marca onboarding como concluído no primeiro agendamento criado
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.onboarding_step != "completed":
            tenant.onboarding_step = "completed"

        db.commit()

        return self.repo.get_with_relations(db, appointment.id)

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
    
    def list_by_tenant(
        self,
        db: Session,
        tenant_id: int,
        start_date=None,
        end_date=None,
    ):
        return self.repo.list_by_tenant(db, tenant_id, start_date=start_date, end_date=end_date)

    # ---------- UPDATE ----------
    def update(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        data: AppointmentUpdate,
    ):
        appointment = self.get(db, tenant_id, appointment_id)

        # 🔹 Atualizar campos simples
        if data.scheduled_at is not None:
            appointment.scheduled_at = data.scheduled_at

        if data.notes is not None:
            appointment.notes = data.notes

        # 🔹 Se vier items → reconstruir
        if data.items is not None:

            # Remove todos os items antigos
            self.repo.delete_items(db, appointment)

            # Recria baseado no payload
            for item in data.items:

                self._validate_pet(
                    db,
                    tenant_id,
                    appointment.client_id,
                    item.pet_id,
                )

                services = self._get_services(
                    db,
                    tenant_id,
                    item.service_ids,
                )

                self.repo.create_item(
                    db=db,
                    appointment=appointment,
                    pet_id=item.pet_id,
                    services=services,
                )

        db.commit()

        return self.repo.get_with_relations(db, appointment.id)
        
    def assign_employees(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        assignments: list,
    ):
        appointment = self.get(db, tenant_id, appointment_id)
        return self.repo.assign_employees(db, appointment.id, assignments)

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
    def _validate_pet(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
    ):
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

        result = self.repo.save_action(db, appointment)

        # Ao completar, desconta créditos de pacotes e registra coverages (FIFO)
        if action == AppointmentAction.COMPLETE:
            appointment_full = self.repo.get_with_relations(db, appointment.id)
            for item in appointment_full.items:
                for service in item.services:
                    credit = self.credit_repo.find_active_credit(
                        db, tenant_id, item.pet_id, service.id
                    )
                    if credit:
                        self.credit_repo.consume_credit(db, credit)
                        self.repo.create_coverage(
                            db,
                            appointment_item_id=item.id,
                            service_id=service.id,
                            client_package_credit_id=credit.id,
                        )
            db.commit()
            # Recarrega com as coverages para o response final
            result = self.repo.get_with_relations(db, appointment.id)

        return result

    def list_open_invoices(self, db: Session, tenant_id: int):
        return self.repo.list_open_invoices(db, tenant_id)
