from datetime import date, datetime
from sqlalchemy.orm import Session,joinedload
from sqlalchemy import func

from .models import Appointment
from app.modules.tenant_services.models import Service


class AppointmentRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
        scheduled_at: datetime,
        services: list[Service],
        notes: str | None = None,
    ) -> Appointment:
        appointment = Appointment(
            tenant_id=tenant_id,
            client_id=client_id,
            pet_id=pet_id,
            scheduled_at=scheduled_at,
            services=services,
            notes=notes,
        )
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        return appointment

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
        return (
            db.query(Appointment)
            .options(
                joinedload(Appointment.client),
                joinedload(Appointment.pet),
                joinedload(Appointment.services),
            )
            .filter(
                Appointment.tenant_id == tenant_id,
                func.date(Appointment.scheduled_at) == day,
            )
            .order_by(Appointment.scheduled_at)
            .all()
        )

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

    def update(
        self,
        db: Session,
        appointment: Appointment,
        scheduled_at: datetime | None = None,
        services: list[Service] | None = None,
    ) -> Appointment:
        if scheduled_at:
            appointment.scheduled_at = scheduled_at

        if services is not None:
            appointment.services = services

        db.commit()
        db.refresh(appointment)
        return appointment

    def delete(self, db: Session, appointment: Appointment):
        db.delete(appointment)
        db.commit()

    def save_action(self, db: Session, appointment: Appointment) -> Appointment:
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        return appointment