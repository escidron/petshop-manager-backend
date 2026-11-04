from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from app.modules.daycare.models import (
    DaycareModality,
    DaycarePackage,
    DaycareStay,
    DaycareTask,
    PetHealthRecord,
)
from app.modules.daycare.schemas import (
    DaycareModalityCreate,
    DaycareModalityResponse,
    DaycareModalityUpdate,
    DaycarePackageCreate,
    DaycarePackageResponse,
    DaycarePackageUpdate,
    DaycareReportUpdateRequest,
    DaycareStayActionRequest,
    DaycareStayCreate,
    DaycareStayResponse,
    DaycareStayUpdate,
    DaycareTaskCreate,
    DaycareTaskResponse,
    DaycareTaskUpdate,
    PetHealthRecordCreate,
    PetHealthRecordResponse,
)
from app.modules.daycare.service import DaycareService

_SCHEMA_ENSURED = False


def ensure_daycare_schema(db: Session = Depends(get_db)) -> None:
    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED:
        return
    bind = db.get_bind()
    DaycareModality.__table__.create(bind=bind, checkfirst=True)
    DaycarePackage.__table__.create(bind=bind, checkfirst=True)
    db.execute(
        text(
            "ALTER TABLE daycare_modalities ADD COLUMN IF NOT EXISTS species JSON;"
        )
    )
    DaycareStay.__table__.create(bind=bind, checkfirst=True)
    db.execute(
        text(
            "ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS modality_id INTEGER REFERENCES daycare_modalities(id) ON DELETE SET NULL;"
        )
    )
    db.execute(
        text(
            "ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS unit_price_cents INTEGER NOT NULL DEFAULT 0;"
        )
    )
    db.execute(
        text(
            "ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS total_price_cents INTEGER NOT NULL DEFAULT 0;"
        )
    )
    db.execute(
        text(
            "ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS report_data JSON;"
        )
    )
    db.commit()
    DaycareTask.__table__.create(bind=bind, checkfirst=True)
    PetHealthRecord.__table__.create(bind=bind, checkfirst=True)
    _SCHEMA_ENSURED = True


router = APIRouter(
    prefix="/daycare",
    tags=["Daycare"],
    dependencies=[Depends(get_current_tenant), Depends(ensure_daycare_schema)],
)


# ---------- MODALIDADES E PREÇOS DA CRECHE ----------
@router.get(
    "/modalities",
    response_model=List[DaycareModalityResponse],
)
@router.get(
    "/modalities/",
    response_model=List[DaycareModalityResponse],
    include_in_schema=False,
)
def list_daycare_modalities(
    request: Request,
    db: Session = Depends(get_db),
    only_active: bool = Query(False),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_modalities(db, tenant_id, only_active=only_active)


@router.post(
    "/modalities",
    response_model=DaycareModalityResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.post(
    "/modalities/",
    response_model=DaycareModalityResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def create_daycare_modality(
    data: DaycareModalityCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().create_modality(db, tenant_id, data)


@router.put(
    "/modalities/{modality_id}",
    response_model=DaycareModalityResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.patch(
    "/modalities/{modality_id}",
    response_model=DaycareModalityResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def update_daycare_modality(
    modality_id: int,
    data: DaycareModalityUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().update_modality(db, tenant_id, modality_id, data)


@router.delete(
    "/modalities/{modality_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
)
@router.delete(
    "/modalities/{modality_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def delete_daycare_modality(
    modality_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    DaycareService().delete_modality(db, tenant_id, modality_id)
    return None


# ---------- PACOTES E MENSALIDADES DA CRECHE ----------
@router.get(
    "/packages",
    response_model=List[DaycarePackageResponse],
)
@router.get(
    "/packages/",
    response_model=List[DaycarePackageResponse],
    include_in_schema=False,
)
def list_daycare_packages(
    request: Request,
    db: Session = Depends(get_db),
    only_active: bool = Query(False),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_packages(db, tenant_id, only_active=only_active)


@router.post(
    "/packages",
    response_model=DaycarePackageResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.post(
    "/packages/",
    response_model=DaycarePackageResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def create_daycare_package(
    data: DaycarePackageCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().create_package(db, tenant_id, data)


@router.put(
    "/packages/{package_id}",
    response_model=DaycarePackageResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.patch(
    "/packages/{package_id}",
    response_model=DaycarePackageResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def update_daycare_package(
    package_id: int,
    data: DaycarePackageUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().update_package(db, tenant_id, package_id, data)


@router.delete(
    "/packages/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
)
@router.delete(
    "/packages/{package_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def delete_daycare_package(
    package_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    DaycareService().delete_package(db, tenant_id, package_id)
    return None


# ---------- AGENDAMENTOS E ESTADIAS DA CRECHE ----------
@router.post(
    "/",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.post(
    "",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def create_daycare_stay(
    data: DaycareStayCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().create(db, tenant_id, data)


@router.get(
    "/highlighted-days",
    response_model=List[date],
)
def list_daycare_highlighted_days(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_highlighted_days(
        db, tenant_id, start_date=start_date, end_date=end_date
    )


@router.get(
    "/day/{day}",
    response_model=List[DaycareStayResponse],
)
def list_daycare_stays_by_day(
    day: date,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_by_day(db, tenant_id, day)


@router.get(
    "/",
    response_model=List[DaycareStayResponse],
)
@router.get(
    "",
    response_model=List[DaycareStayResponse],
    include_in_schema=False,
)
def list_daycare_stays(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_by_range(db, tenant_id, start_date=start_date, end_date=end_date)


@router.get(
    "/{stay_id}",
    response_model=DaycareStayResponse,
)
def get_daycare_stay(
    stay_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().get(db, tenant_id, stay_id)


@router.put(
    "/{stay_id}",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.patch(
    "/{stay_id}",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def update_daycare_stay(
    stay_id: int,
    data: DaycareStayUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().update(db, tenant_id, stay_id, data)


@router.patch(
    "/{stay_id}/report",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
)
@router.patch(
    "/stays/{stay_id}/report",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
    include_in_schema=False,
)
def update_daycare_report(
    stay_id: int,
    data: DaycareReportUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().update_report(db, tenant_id, stay_id, data.report_data)


@router.delete(
    "/{stay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
)
def delete_daycare_stay(
    stay_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    DaycareService().delete(db, tenant_id, stay_id)
    return None


@router.post(
    "/{stay_id}/action",
    response_model=DaycareStayResponse,
    dependencies=[Depends(require_active_subscription)],
)
def apply_daycare_stay_action(
    stay_id: int,
    data: DaycareStayActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().apply_action(db, tenant_id, stay_id, data.action, data.notes)


# ---------- TASKS (RAÇÃO E REMÉDIOS) ----------
@router.post(
    "/{stay_id}/tasks",
    response_model=DaycareTaskResponse,
    dependencies=[Depends(require_active_subscription)],
)
def add_daycare_task(
    stay_id: int,
    data: DaycareTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().add_task(db, tenant_id, stay_id, data)


@router.patch(
    "/tasks/{task_id}",
    response_model=DaycareTaskResponse,
    dependencies=[Depends(require_active_subscription)],
)
def update_daycare_task(
    task_id: int,
    data: DaycareTaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().update_task(db, tenant_id, task_id, data)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
)
def delete_daycare_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    DaycareService().delete_task(db, tenant_id, task_id)
    return None


# ---------- SAÚDE / VACINAS ----------
@router.post(
    "/health-records",
    response_model=PetHealthRecordResponse,
    dependencies=[Depends(require_active_subscription)],
)
def create_pet_health_record(
    data: PetHealthRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().create_health_record(db, tenant_id, data)


@router.get(
    "/health-records/pet/{pet_id}",
    response_model=List[PetHealthRecordResponse],
)
def list_pet_health_records(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return DaycareService().list_health_records_by_pet(db, tenant_id, pet_id)


@router.delete(
    "/health-records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_subscription)],
)
def delete_pet_health_record(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    DaycareService().delete_health_record(db, tenant_id, record_id)
    return None
