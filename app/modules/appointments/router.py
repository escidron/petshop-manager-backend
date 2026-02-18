from datetime import date
import json
from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import (
    AppointmentActionRequest,
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
)
from .service import AppointmentService

router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
    dependencies=[Depends(get_current_tenant)],

)


@router.post("/", response_model=AppointmentResponse)
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
    appointments = AppointmentService().list_by_day(db, tenant_id, day)
    encoded = jsonable_encoder(appointments)

    print(json.dumps(encoded, indent=2, ensure_ascii=False))
    return appointments


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


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
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


@router.delete("/{appointment_id}", status_code=204)
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
):
    tenant_id = request.state.tenant_user.tenant_id
    return AppointmentService().apply_action(
        db=db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        action=data.action,
    )