from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr


EmployeeRole = Literal["groomer", "bather", "salesperson", "receptionist", "driver", "vet", "other"]


class EmployeeBase(BaseModel):
    name: str
    role: EmployeeRole = "other"
    phone: str
    email: Optional[EmailStr] = None
    is_active: bool = True


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[EmployeeRole] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class EmployeeResponse(EmployeeBase):
    id: int
    tenant_id: int
    schedule_token: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PublicAppointmentService(BaseModel):
    id: int
    name: str
    duration_minutes: Optional[int] = None


class PublicAppointmentPet(BaseModel):
    id: int
    name: str
    species: str
    breed: Optional[str] = None


class PublicAppointmentItem(BaseModel):
    id: int
    pet: PublicAppointmentPet
    services: list[PublicAppointmentService]


class PublicAppointment(BaseModel):
    id: int
    scheduled_at: datetime
    status: str
    notes: Optional[str] = None
    client_name: str
    client_phone: Optional[str] = None
    items: list[PublicAppointmentItem]


class PublicFreelancerScheduleResponse(BaseModel):
    employee_name: str
    employee_role: str
    petshop_name: str
    appointments: list[PublicAppointment]


class PublicBookingRequest(BaseModel):
    client_name: str
    client_phone: str
    pet_name: str
    service_ids: list[int]
    scheduled_at: datetime
    notes: Optional[str] = None


class PublicBookingResponse(BaseModel):
    success: bool
    appointment_id: int
    message: str


