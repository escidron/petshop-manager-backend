from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.client_packages.models import ClientPackage
from app.modules.daycare.models import (
    DaycareStay,
    DaycareStayStatus,
    DaycareTask,
    PetHealthRecord,
)
from app.modules.pets.models import Pet
from app.utils.timezone import (
    get_date_range_bounds_brazil,
    get_day_bounds_brazil,
    to_brazil_datetime,
)


def _stay_eager_options():
    return [
        joinedload(DaycareStay.client),
        joinedload(DaycareStay.pet).options(
            selectinload(Pet.photos),
            selectinload(Pet.client_packages).selectinload(ClientPackage.credits),
        ),
        joinedload(DaycareStay.modality),
        joinedload(DaycareStay.package),
        joinedload(DaycareStay.service),
        selectinload(DaycareStay.tasks),
    ]


class DaycareRepository:
    def create_stay(self, db: Session, stay: DaycareStay) -> DaycareStay:
        db.add(stay)
        db.flush()
        return stay

    def get_by_id(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
    ) -> Optional[DaycareStay]:
        return (
            db.query(DaycareStay)
            .options(*_stay_eager_options())
            .filter(
                DaycareStay.id == stay_id,
                DaycareStay.tenant_id == tenant_id,
            )
            .first()
        )

    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ) -> List[DaycareStay]:
        day_start, day_end = get_day_bounds_brazil(day)
        return (
            db.query(DaycareStay)
            .options(*_stay_eager_options())
            .filter(
                DaycareStay.tenant_id == tenant_id,
                DaycareStay.scheduled_start_at <= day_end,
                DaycareStay.scheduled_end_at >= day_start,
            )
            .order_by(DaycareStay.scheduled_start_at.asc(), DaycareStay.id.asc())
            .all()
        )

    def list_by_range(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[DaycareStay]:
        start_dt, end_dt = get_date_range_bounds_brazil(start_date, end_date)
        query = (
            db.query(DaycareStay)
            .options(*_stay_eager_options())
            .filter(DaycareStay.tenant_id == tenant_id)
        )
        if start_dt is not None:
            query = query.filter(DaycareStay.scheduled_end_at >= start_dt)
        if end_dt is not None:
            query = query.filter(DaycareStay.scheduled_start_at <= end_dt)
        return query.order_by(DaycareStay.scheduled_start_at.asc(), DaycareStay.id.asc()).all()

    def list_highlighted_days(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[date]:
        start_dt, end_dt = get_date_range_bounds_brazil(start_date, end_date)
        query = (
            db.query(
                DaycareStay.scheduled_start_at,
                DaycareStay.scheduled_end_at,
            )
            .filter(
                DaycareStay.tenant_id == tenant_id,
                DaycareStay.status != DaycareStayStatus.CANCELED.value,
            )
        )
        if start_dt is not None:
            query = query.filter(DaycareStay.scheduled_end_at >= start_dt)
        if end_dt is not None:
            query = query.filter(DaycareStay.scheduled_start_at <= end_dt)

        rows = query.all()
        days_set: set[date] = set()
        for start_at, end_at in rows:
            br_start = to_brazil_datetime(start_at).date()
            br_end = to_brazil_datetime(end_at).date()
            if start_date and br_start < start_date:
                br_start = start_date
            if end_date and br_end > end_date:
                br_end = end_date
            curr = br_start
            while curr <= br_end:
                days_set.add(curr)
                curr += timedelta(days=1)

        return sorted(days_set)

    def get_task_by_id(
        self,
        db: Session,
        tenant_id: int,
        task_id: int,
    ) -> Optional[DaycareTask]:
        return (
            db.query(DaycareTask)
            .filter(
                DaycareTask.id == task_id,
                DaycareTask.tenant_id == tenant_id,
            )
            .first()
        )

    def list_health_records_by_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ) -> List[PetHealthRecord]:
        return (
            db.query(PetHealthRecord)
            .filter(
                PetHealthRecord.tenant_id == tenant_id,
                PetHealthRecord.pet_id == pet_id,
            )
            .order_by(PetHealthRecord.expires_at.asc().nulls_last(), PetHealthRecord.applied_at.desc())
            .all()
        )

