from datetime import datetime
from pydantic import BaseModel, Field
from typing import List

from app.modules.appointments.models import (
    AppointmentAction,
    AppointmentStatus,
)
from app.modules.clients.schemas import ClientBase
from app.modules.pets.schemas import PetBase
from app.modules.tenant_services.schemas import ServiceBase

class AppointmentItemCreate(BaseModel):
    pet_id: int
    service_ids: List[int] = Field(
        min_length=1,
        description="Lista de serviços para esse pet",
    )


class AppointmentItemResponse(BaseModel):
    id: int
    pet: PetBase
    services: List[ServiceBase]

    class Config:
        from_attributes = True


class AppointmentCreate(BaseModel):
    client_id: int
    scheduled_at: datetime
    notes: str | None = None

    items: List[AppointmentItemCreate] = Field(
        min_length=1,
        description="Lista de pets com seus respectivos serviços",
    )


class AppointmentUpdate(BaseModel):
    scheduled_at: datetime | None = None
    notes: str | None = None
    items: List[AppointmentItemCreate] | None = None


class AppointmentResponse(BaseModel):
    id: int
    scheduled_at: datetime
    notes: str | None = None
    status: AppointmentStatus

    client: ClientBase
    items: List[AppointmentItemResponse]

    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# Appointment Action Schema
# ============================================================

class AppointmentActionRequest(BaseModel):
    action: AppointmentAction
