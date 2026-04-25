from datetime import date
from fastapi import APIRouter, Depends, Request, Query
from typing import Optional
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    AppointmentActionRequest,
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AppointmentEmployeeAssignmentRequest,
)
from .service import AppointmentService

router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
    dependencies=[Depends(get_current_tenant)],

)


@router.post("/", response_model=AppointmentResponse, dependencies=[Depends(require_active_subscription)])
def create_appointment(
    data: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().create(db, tenant_id, data)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().get(
        db, tenant_id, appointment_id
    )


@router.get(
    "/day/{day}",
    response_model=list[AppointmentResponse],
)
def list_appointments_by_day(
    day: date,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().list_by_day(db, tenant_id, day)


@router.get(
    "/client/{client_id}",
    response_model=list[AppointmentResponse],
)
def list_appointments_by_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().list_by_client(
        db, tenant_id, client_id
    )

@router.get(
    "/",
    response_model=list[AppointmentResponse],
)
def list_appointments_by_tenant(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().list_by_tenant(
        db, tenant_id, start_date=start_date, end_date=end_date
    )


@router.patch("/{appointment_id}", response_model=AppointmentResponse, dependencies=[Depends(require_active_subscription)])
def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().update(
        db, tenant_id, appointment_id, data
    )


@router.patch("/{appointment_id}/assign-employees", response_model=AppointmentResponse, dependencies=[Depends(require_active_subscription)])
def assign_appointment_employees(
    appointment_id: int,
    data: AppointmentEmployeeAssignmentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().assign_employees(
        db, tenant_id, appointment_id, data.assignments
    )

@router.delete("/{appointment_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    AppointmentService().delete(
        db, tenant_id, appointment_id
    )

@router.post(
    "/{appointment_id}/actions",
    response_model=AppointmentResponse,
)
def appointment_action(
    appointment_id: int,
    data: AppointmentActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    tenant_ctx: dict = Depends(get_current_tenant),
):
    from app.modules.appointments.models import AppointmentAction
    
    if data.action != AppointmentAction.CANCEL:
        require_active_subscription(tenant_ctx)

    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().apply_action(
        db=db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        action=data.action,
    )