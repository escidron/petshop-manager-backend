from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

from app.modules.appointments.models import (
    AppointmentAction,
    AppointmentStatus,
)
from app.modules.clients.schemas import ClientSummaryResponse
from app.modules.pets.schemas import PetResponse


class PaginatedAppointmentsResponse(BaseModel):
    items: List["AppointmentResponse"]
    total: int

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
    billing_status: str = "active"
    is_removed: bool = False
    removed_at: datetime | None = None
    removal_reason: str | None = None
    employee_id: int | None = None
    species: str | None = None
    size: str | None = None
    coat_type: str | None = None

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

        # Se ainda não foi finalizado/coberto, verifica se o pet possui créditos ativos de pacote para o serviço
        available_package_service_ids = set()
        pet = getattr(data, "pet", None)
        appointment = getattr(data, "appointment", None)
        appt_status = getattr(appointment, "status", None) if appointment else None
        if pet and not covered_ids and appt_status not in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELED, "completed", "canceled"]:
            client_pkgs = getattr(pet, "client_packages", []) or []
            from datetime import timezone
            now = datetime.now(timezone.utc)
            for pkg in client_pkgs:
                if not getattr(pkg, "is_active", False):
                    continue
                exp = getattr(pkg, "expires_at", None)
                if exp is not None:
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    if exp <= now:
                        continue
                for credit in getattr(pkg, "credits", []) or []:
                    if credit.service_id and (credit.total_qty - credit.used_qty) > 0:
                        available_package_service_ids.add(credit.service_id)

        item_services = getattr(data, "item_services", []) or []
        emp_map = {item_svc.service_id: item_svc.employee_id for item_svc in item_services}
        status_map = {item_svc.service_id: getattr(item_svc, "status", "active") for item_svc in item_services}
        removed_at_map = {item_svc.service_id: getattr(item_svc, "removed_at", None) for item_svc in item_services}
        removal_reason_map = {item_svc.service_id: getattr(item_svc, "removal_reason", None) for item_svc in item_services}

        services_data = [
            {
                "id": svc.id,
                "name": svc.name,
                "price_cents": svc.price_cents,
                "duration_minutes": getattr(svc, "duration_minutes", None),
                "is_package_covered": (svc.id in covered_ids) or (svc.id in available_package_service_ids),
                "billing_status": status_map.get(svc.id, "active"),
                "is_removed": status_map.get(svc.id, "active") in ("removed", "canceled"),
                "removed_at": removed_at_map.get(svc.id),
                "removal_reason": removal_reason_map.get(svc.id),
                "employee_id": emp_map.get(svc.id),
                "species": getattr(svc, "species", None),
                "size": getattr(svc, "size", None),
                "coat_type": getattr(svc, "coat_type", None),
            }
            for svc in data.services
        ]
        return {"id": data.id, "pet": data.pet, "services": services_data}


class AppointmentRecurrence(BaseModel):
    frequency: str = Field(description="'weekly', 'biweekly', or 'monthly'")
    occurrences: int = Field(ge=2, le=52, description="Number of times to repeat")


class AppointmentRecurrenceInfo(BaseModel):
    frequency: str = Field(description="'weekly', 'biweekly', or 'monthly'")
    occurrences: int = Field(description="Number of remaining occurrences in the series")


class AppointmentCreate(BaseModel):
    client_id: int
    scheduled_at: datetime
    notes: str | None = None

    items: List[AppointmentItemCreate] = Field(
        min_length=1,
        description="Lista de pets com seus respectivos serviços",
    )
    recurrence: AppointmentRecurrence | None = None


class AppointmentUpdate(BaseModel):
    scheduled_at: datetime | None = None
    notes: str | None = None
    items: List[AppointmentItemCreate] | None = None
    update_all_future: bool = False
    recurrence: AppointmentRecurrence | None = None
    remove_recurrence: bool = False


class AppointmentAuditLogResponse(BaseModel):
    id: int
    appointment_id: int
    service_id: int | None = None
    service_name: str | None = None
    pet_name: str | None = None
    action: str
    notes: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentResponse(BaseModel):
    id: int
    scheduled_at: datetime
    notes: str | None = None
    status: AppointmentStatus

    client: ClientSummaryResponse
    items: List[AppointmentItemResponse]
    is_paid: bool = False
    is_fully_package_covered: bool = False
    warnings: List[str] = Field(default_factory=list)
    recurrence_id: str | None = None
    recurrence_frequency: str | None = None
    recurrence: AppointmentRecurrenceInfo | None = None

    audit_logs: List[AppointmentAuditLogResponse] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def compute_package_coverage(self) -> "AppointmentResponse":
        if self.is_paid or not self.items:
            return self
        # Considera apenas serviços ativos (ignora serviços removidos do faturamento no PDV)
        active_services = [
            s for item in self.items for s in item.services if not getattr(s, "is_removed", False)
        ]
        if active_services and all(s.is_package_covered for s in active_services):
            self.is_fully_package_covered = True
        elif not active_services and any(s.is_removed for item in self.items for s in item.services):
            # Se todos os serviços foram dispensados/removidos, não há pendência de cobrança
            self.is_fully_package_covered = True
        return self


# ============================================================
# Appointment Action Schema
# ============================================================

class AppointmentActionRequest(BaseModel):
    action: AppointmentAction
    cancel_all_future: bool = False


# ============================================================
# Assignment Schema
# ============================================================

class ServiceEmployeeAssignment(BaseModel):
    appointment_item_id: int
    service_id: int
    employee_id: int | None

class AppointmentEmployeeAssignmentRequest(BaseModel):
    assignments: List[ServiceEmployeeAssignment]


class CancelCompletedAppointmentRequest(BaseModel):
    reason: Optional[str] = None


class AddAppointmentServiceRequest(BaseModel):
    pet_id: int
    service_id: int
    employee_id: Optional[int] = None
