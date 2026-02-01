from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
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
)


@router.post("/", response_model=AppointmentResponse)
def create_appointment(
    tenant_id: int,
    data: AppointmentCreate,
    db: Session = Depends(get_db),
):
    return AppointmentService().create(db, tenant_id, data)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    tenant_id: int,
    appointment_id: int,
    db: Session = Depends(get_db),
):

    return AppointmentService().get(
        db, tenant_id, appointment_id
    )


@router.get(
    "/day/{day}",
    response_model=list[AppointmentResponse],
)
def list_appointments_by_day(
    tenant_id: int,
    day: date,
    db: Session = Depends(get_db),
):
    return AppointmentService().list_by_day(
        db, tenant_id, day
    )


@router.get(
    "/client/{client_id}",
    response_model=list[AppointmentResponse],
)
def list_appointments_by_client(
    tenant_id: int,
    client_id: int,
    db: Session = Depends(get_db),
):

    return AppointmentService().list_by_client(
        db, tenant_id, client_id
    )


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    tenant_id: int,
    appointment_id: int,
    data: AppointmentUpdate,
    db: Session = Depends(get_db),
):

    return AppointmentService().update(
        db, tenant_id, appointment_id, data
    )


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(
    tenant_id: int,
    appointment_id: int,
    db: Session = Depends(get_db),
):
    AppointmentService().delete(
        db, tenant_id, appointment_id
    )

@router.post(
    "/{appointment_id}/actions",
    response_model=AppointmentResponse,
)
def appointment_action(
    tenant_id: int,
    appointment_id: int,
    data: AppointmentActionRequest,
    db: Session = Depends(get_db),
):
    return AppointmentService().apply_action(
        db=db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        action=data.action,
    )