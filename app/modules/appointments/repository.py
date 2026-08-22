from datetime import date, datetime, time
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func

from .models import Appointment, AppointmentItem, AppointmentPackageCoverage
from app.modules.tenant_services.models import Service


from app.modules.pets.models import Pet

def _eager_options():
    """Opções de eager loading reutilizáveis para evitar N+1."""
    return [
        joinedload(Appointment.client),                          # many-to-one → joinedload ok
        selectinload(Appointment.sales),                         # one-to-many → selectinload
        selectinload(Appointment.items)                          # one-to-many → selectinload
            .joinedload(AppointmentItem.pet)                     # many-to-one dentro do item
            .selectinload(Pet.photos),                           # one-to-many (pet.photos)
        selectinload(Appointment.items)
            .selectinload(AppointmentItem.services),             # many-to-many → selectinload
        selectinload(Appointment.items)
            .selectinload(AppointmentItem.coverages),            # one-to-many → selectinload
        selectinload(Appointment.items)
            .selectinload(AppointmentItem.item_services),        # employee_id por serviço
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
            .options(*_eager_options())
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

    def assign_employees(
        self,
        db: Session,
        appointment_id: int,
        assignments: list,
    ) -> Appointment:
        from .models import AppointmentItemService
        for assignment in assignments:
            db.query(AppointmentItemService).filter(
                AppointmentItemService.appointment_item_id == assignment.appointment_item_id,
                AppointmentItemService.service_id == assignment.service_id,
            ).update({"employee_id": assignment.employee_id}, synchronize_session=False)
        db.commit()
        return self.get_with_relations(db, appointment_id)
        
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

    def list_open_invoices(
        self,
        db: Session,
        tenant_id: int,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> tuple[list[Appointment], int]:
        """Appointments completed but not yet paid — the 'open tabs'.

        is_paid is a Python property (not a DB column), so we use a NOT EXISTS
        subquery against the sales table to detect unpaid appointments.
        Appointments fully covered by packages are also excluded (no payment needed).
        """
        from app.modules.sales.models import Sale
        from .models import AppointmentItem, AppointmentItemService, AppointmentPackageCoverage
        from app.modules.clients.models import Client
        from app.modules.pets.models import Pet

        # Subquery: any completed sale linked to this appointment?
        paid_subquery = (
            db.query(Sale.id)
            .filter(
                Sale.appointment_id == Appointment.id,
                Sale.status == "completed",
                Sale.payment_method != "package",
            )
            .exists()
        )

        # Subquery: does this appointment have at least one service NOT covered by a package?
        # If all services have coverage records, no payment is needed.
        has_uncovered_service = (
            db.query(AppointmentItemService.service_id)
            .join(AppointmentItem, AppointmentItem.id == AppointmentItemService.appointment_item_id)
            .outerjoin(
                AppointmentPackageCoverage,
                (AppointmentPackageCoverage.appointment_item_id == AppointmentItemService.appointment_item_id)
                & (AppointmentPackageCoverage.service_id == AppointmentItemService.service_id),
            )
            .filter(
                AppointmentItem.appointment_id == Appointment.id,
                AppointmentPackageCoverage.id == None,  # no coverage for this service
            )
            .exists()
        )

        query = db.query(Appointment).filter(
            Appointment.tenant_id == tenant_id,
            Appointment.status == "completed",
            ~paid_subquery,       # no completed sale attached
            has_uncovered_service,  # at least one service still needs payment
        )

        if search:
            search_term = f"%{search}%"
            query = query.outerjoin(Client, Appointment.client_id == Client.id)
            query = query.outerjoin(AppointmentItem, Appointment.id == AppointmentItem.appointment_id)
            query = query.outerjoin(Pet, AppointmentItem.pet_id == Pet.id)
            query = query.filter(
                (Client.name.ilike(search_term)) | (Pet.name.ilike(search_term))
            )

        total = query.count()

        query = query.options(*_eager_options()).order_by(Appointment.scheduled_at.desc())

        if limit is not None:
            query = query.limit(limit).offset(offset)

        return query.all(), total

    def list_highlighted_days(
        self,
        db: Session,
        tenant_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[date]:
        from sqlalchemy import Date, cast
        q = (
            db.query(cast(Appointment.scheduled_at, Date))
            .filter(Appointment.tenant_id == tenant_id)
        )
        if start_date:
            q = q.filter(Appointment.scheduled_at >= datetime.combine(start_date, time.min))
        if end_date:
            q = q.filter(Appointment.scheduled_at <= datetime.combine(end_date, time.max))
        
        results = q.distinct().order_by(cast(Appointment.scheduled_at, Date)).all()
        return [r[0] for r in results if r[0] is not None]