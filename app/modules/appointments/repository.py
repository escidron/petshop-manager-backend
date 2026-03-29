from datetime import date, datetime, time
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func

from .models import Appointment, AppointmentItem, AppointmentPackageCoverage
from app.modules.tenant_services.models import Service


def _eager_options():
    """Opções de eager loading reutilizáveis para evitar N+1."""
    return [
        joinedload(Appointment.client),                          # many-to-one → joinedload ok
        selectinload(Appointment.items)                          # one-to-many → selectinload
            .joinedload(AppointmentItem.pet),                    # many-to-one dentro do item
        selectinload(Appointment.items)
            .selectinload(AppointmentItem.services),             # many-to-many → selectinload
        selectinload(Appointment.items)
            .selectinload(AppointmentItem.coverages),            # one-to-many → selectinload
    ]


class AppointmentRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        scheduled_at: datetime,
        notes: str | None = None,
    ) -> Appointment:

        appointment = Appointment(
            tenant_id=tenant_id,
            client_id=client_id,
            scheduled_at=scheduled_at,
            notes=notes,
        )

        db.add(appointment)
        db.flush()  # importante para gerar ID antes dos items

        return appointment
    
    def create_item(
        self,
        db: Session,
        appointment: Appointment,
        pet_id: int,
        services: list[Service],
    ) -> AppointmentItem:

        item = AppointmentItem(
            appointment_id=appointment.id,
            pet_id=pet_id,
            services=services,
        )

        db.add(item)
        return item

    def get_by_id(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
    ) -> Appointment | None:
        return (
            db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.tenant_id == tenant_id,
            )
            .first()
        )


    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ) -> list[Appointment]:
        # Usa range em vez de func.date() para aproveitar o índice em scheduled_at
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        return (
            db.query(Appointment)
            .options(*_eager_options())
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.scheduled_at >= start,
                Appointment.scheduled_at <= end,
            )
            .order_by(Appointment.scheduled_at)
            .all()
        )

    def create_coverage(
        self,
        db: Session,
        appointment_item_id: int,
        service_id: int,
        client_package_credit_id: int | None,
    ) -> AppointmentPackageCoverage:
        coverage = AppointmentPackageCoverage(
            appointment_item_id=appointment_item_id,
            service_id=service_id,
            client_package_credit_id=client_package_credit_id,
        )
        db.add(coverage)
        return coverage

    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ) -> list[Appointment]:
        return (
            db.query(Appointment)
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.client_id == client_id,
            )
            .order_by(Appointment.scheduled_at.desc())
            .all()
        )
    
    def list_by_tenant(
        self,
        db: Session,
        tenant_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Appointment]:
        q = (
            db.query(Appointment)
            .options(*_eager_options())
            .filter(Appointment.tenant_id == tenant_id)
        )
        if start_date:
            q = q.filter(Appointment.scheduled_at >= datetime.combine(start_date, time.min))
        if end_date:
            q = q.filter(Appointment.scheduled_at <= datetime.combine(end_date, time.max))
        return q.order_by(Appointment.scheduled_at.desc()).all()

    def update(
        self,
        db: Session,
        appointment: Appointment,
        scheduled_at: datetime | None = None,
        notes: str | None = None,
    ) -> Appointment:

        if scheduled_at is not None:
            appointment.scheduled_at = scheduled_at

        if notes is not None:
            appointment.notes = notes

        db.add(appointment)
        db.flush()

        return appointment

    def delete(self, db: Session, appointment: Appointment):
        db.delete(appointment)
        db.commit()

    def delete_items(
        self,
        db: Session,
        appointment: Appointment,
    ):
        for item in appointment.items:
            db.delete(item)

        db.flush()
        
    def save_action(self, db: Session, appointment: Appointment) -> Appointment:
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        return appointment
    
    def get_with_relations(
        self,
        db: Session,
        appointment_id: int,
    ) -> Appointment:
        return (
            db.query(Appointment)
            .options(*_eager_options())
            .filter(Appointment.id == appointment_id)
            .first()
        )