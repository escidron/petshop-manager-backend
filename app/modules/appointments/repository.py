from datetime import date, datetime
from sqlalchemy.orm import Session,joinedload, selectinload
from sqlalchemy import func

from .models import Appointment, AppointmentItem
from app.modules.tenant_services.models import Service


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

        return (
            db.query(Appointment)
            .options(
                joinedload(Appointment.client),
                joinedload(Appointment.items)
                    .joinedload(AppointmentItem.pet),
                joinedload(Appointment.items)
                    .joinedload(AppointmentItem.services),
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

        appointment = (
            db.query(Appointment)
            .options(
                selectinload(Appointment.client),
                selectinload(Appointment.items)
                .selectinload(AppointmentItem.pet),
                selectinload(Appointment.items)
                .selectinload(AppointmentItem.services),
            )
            .filter(Appointment.id == appointment_id)
            .first()
        )

        return appointment