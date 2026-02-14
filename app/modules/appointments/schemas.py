from datetime import datetime
from pydantic import BaseModel

from app.modules.appointments.models import AppointmentAction, AppointmentStatus
from app.modules.clients.schemas import ClientBase
from app.modules.pets.schemas import PetBase


class AppointmentCreate(BaseModel):
    client_id: int
    pet_id: int
    scheduled_at: datetime
    service_ids: list[int]
    notes: str | None


class AppointmentUpdate(BaseModel):
    scheduled_at: datetime | None = None
    service_ids: list[int] | None = None
    notes: str | None = None


class AppointmentResponse(BaseModel):
    id: int
    scheduled_at: datetime
    notes: str | None = None
    client: ClientBase
    pet: PetBase
    services: list[int]
    status: AppointmentStatus

    class Config:
        from_attributes = True

class AppointmentActionRequest(BaseModel):
    action: AppointmentAction