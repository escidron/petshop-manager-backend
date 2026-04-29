from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr


EmployeeRole = Literal["groomer", "bather", "salesperson", "other"]


class EmployeeBase(BaseModel):
    name: str
    role: EmployeeRole = "other"
    phone: Optional[str] = None
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
    created_at: datetime

    class Config:
        from_attributes = True
