from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer

from app.modules.clients.schemas import ClientSummaryResponse
from app.modules.daycare.models import (
    DaycareModalityBillingType,
    DaycareStayAction,
    DaycareStayStatus,
    DaycareStayType,
    DaycareTaskType,
)
from app.modules.pets.schemas import PetResponse
from app.utils.timezone import to_brazil_datetime


class DaycareModalityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    billing_type: DaycareModalityBillingType = DaycareModalityBillingType.DAILY
    description: Optional[str] = None
    max_hours: Optional[int] = Field(default=None, ge=1)
    species: Optional[List[str]] = None
    sizes: Optional[List[str]] = None
    price_cents: int = Field(..., ge=0)
    is_active: bool = True


class DaycareModalityUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    billing_type: Optional[DaycareModalityBillingType] = None
    description: Optional[str] = None
    max_hours: Optional[int] = Field(default=None, ge=1)
    species: Optional[List[str]] = None
    sizes: Optional[List[str]] = None
    price_cents: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class DaycareModalityResponse(BaseModel):
    id: int
    name: str
    billing_type: str
    description: Optional[str] = None
    max_hours: Optional[int] = None
    species: Optional[List[str]] = None
    sizes: Optional[List[str]] = None
    price_cents: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)


class DaycareTaskCreate(BaseModel):
    task_type: DaycareTaskType = DaycareTaskType.FEEDING
    scheduled_time: str = Field(..., min_length=4, max_length=5, description="Horário no formato HH:MM")
    title: str = Field(..., min_length=1, max_length=200)
    notes: Optional[str] = None


class DaycareTaskUpdate(BaseModel):
    task_type: Optional[DaycareTaskType] = None
    scheduled_time: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    is_completed: Optional[bool] = None


class DaycareTaskResponse(BaseModel):
    id: int
    stay_id: int
    task_type: str
    scheduled_time: str
    title: str
    notes: Optional[str] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("completed_at")
    def serialize_completed_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)


class DaycareRecurrenceInput(BaseModel):
    frequency: Optional[str] = Field(default="weekdays", description="daily | weekdays | weekly | biweekly | monthly | custom")
    occurrences: Optional[int] = Field(default=None, ge=1, le=365)
    weekdays: Optional[List[int]] = Field(default=None, description="0=Dom, 1=Seg, 2=Ter, 3=Qua, 4=Qui, 5=Sex, 6=Sab")
    weeks_count: Optional[int] = Field(default=None, ge=1, le=52)
    is_continuous: Optional[bool] = Field(default=False)


class DaycareStayCreate(BaseModel):
    client_id: int
    pet_id: int
    modality_id: Optional[int] = None
    service_id: Optional[int] = None
    stay_type: DaycareStayType = DaycareStayType.DAILY
    quantity: int = Field(default=1, ge=1)
    unit_price_cents: Optional[int] = Field(default=None, ge=0)
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    food_info: Optional[str] = None
    belongings: Optional[str] = None
    notes: Optional[str] = None
    tasks: List[DaycareTaskCreate] = Field(default_factory=list)
    recurrence: Optional[DaycareRecurrenceInput] = None


class DaycareStayUpdate(BaseModel):
    modality_id: Optional[int] = None
    service_id: Optional[int] = None
    stay_type: Optional[DaycareStayType] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    unit_price_cents: Optional[int] = Field(default=None, ge=0)
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    food_info: Optional[str] = None
    belongings: Optional[str] = None
    notes: Optional[str] = None
    tasks: Optional[List[DaycareTaskCreate]] = None


class DaycareStayActionRequest(BaseModel):
    action: DaycareStayAction
    notes: Optional[str] = None


class PetHealthRecordCreate(BaseModel):
    pet_id: int
    category: str = Field(default="vaccine", description="vaccine | antiparasitic | dewormer | exam")
    name: str = Field(..., min_length=1, max_length=150)
    applied_at: date
    expires_at: Optional[date] = None
    notes: Optional[str] = None


class PetHealthRecordResponse(BaseModel):
    id: int
    pet_id: int
    category: str
    name: str
    applied_at: date
    expires_at: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)


class DaycareServiceSummary(BaseModel):
    id: int
    name: str
    price_cents: int
    duration_minutes: Optional[int] = None

    class Config:
        from_attributes = True


class DaycareStayResponse(BaseModel):
    id: int
    client_id: int
    pet_id: int
    modality_id: Optional[int] = None
    service_id: Optional[int] = None
    stay_type: str
    quantity: int
    unit_price_cents: int = 0
    total_price_cents: int = 0
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    status: DaycareStayStatus
    food_info: Optional[str] = None
    belongings: Optional[str] = None
    notes: Optional[str] = None
    recurrence_id: Optional[str] = None
    recurrence_rule: Optional[dict] = None
    covered_quantity: int = 0
    is_package_covered: bool = False
    client: ClientSummaryResponse
    pet: PetResponse
    modality: Optional[DaycareModalityResponse] = None
    service: Optional[DaycareServiceSummary] = None
    tasks: List[DaycareTaskResponse] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("scheduled_start_at")
    def serialize_scheduled_start_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    @field_serializer("scheduled_end_at")
    def serialize_scheduled_end_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    @field_serializer("check_in_at")
    def serialize_check_in_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    @field_serializer("check_out_at")
    def serialize_check_out_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)
