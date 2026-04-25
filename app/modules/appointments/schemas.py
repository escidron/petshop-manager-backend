from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import List

from app.modules.appointments.models import (
    AppointmentAction,
    AppointmentStatus,
)
from app.modules.clients.schemas import ClientResponse
from app.modules.pets.schemas import PetResponse


class AppointmentItemCreate(BaseModel):
    pet_id: int
    service_ids: List[int] = Field(
        min_length=1,
        description="Lista de serviços para esse pet",
    )


class ServiceInAppointmentResponse(BaseModel):
    id: int
    name: str
    price_cents: int
    duration_minutes: int | None = None
    is_package_covered: bool = False
    employee_id: int | None = None

    class Config:
        from_attributes = True


class AppointmentItemResponse(BaseModel):
    id: int
    pet: PetResponse
    services: List[ServiceInAppointmentResponse]

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def attach_coverage(cls, data):
        if isinstance(data, dict):
            return data
        # ORM object: injeta is_package_covered e employee_id em cada serviço
        covered_ids = {c.service_id for c in getattr(data, "coverages", [])}
        emp_map = {item_svc.service_id: item_svc.employee_id for item_svc in getattr(data, "item_services", [])}
        services_data = [
            {
                "id": svc.id,
                "name": svc.name,
                "price_cents": svc.price_cents,
                "duration_minutes": getattr(svc, "duration_minutes", None),
                "is_package_covered": svc.id in covered_ids,
                "employee_id": emp_map.get(svc.id),
            }
            for svc in data.services
        ]
        return {"id": data.id, "pet": data.pet, "services": services_data}


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

    client: ClientResponse
    items: List[AppointmentItemResponse]
    is_paid: bool = False
    is_fully_package_covered: bool = False

    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def compute_package_coverage(self) -> "AppointmentResponse":
        if self.is_paid or not self.items:
            return self
        all_services = [s for item in self.items for s in item.services]
        if all_services and all(s.is_package_covered for s in all_services):
            self.is_fully_package_covered = True
        return self


# ============================================================
# Appointment Action Schema
# ============================================================

class AppointmentActionRequest(BaseModel):
    action: AppointmentAction


# ============================================================
# Assignment Schema
# ============================================================

class ServiceEmployeeAssignment(BaseModel):
    appointment_item_id: int
    service_id: int
    employee_id: int | None

class AppointmentEmployeeAssignmentRequest(BaseModel):
    assignments: List[ServiceEmployeeAssignment]
