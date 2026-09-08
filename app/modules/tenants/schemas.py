from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.modules.subscriptions.schemas import SubscriptionResponse


class TenantBase(BaseModel):
    name: str = Field(..., max_length=150)
    type_id: int = 1
    is_active: bool = True
    phone: str = Field(..., max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    plan_code: str = Field(..., max_length=50)
    onboarding_step: str = Field("services", max_length=50)
    document: Optional[str] = Field(None, max_length=20)
    whatsapp_package: Optional[str] = Field(None, max_length=50)
    cep: Optional[str] = Field(None, max_length=10)
    street: Optional[str] = Field(None, max_length=150)
    number: Optional[str] = Field(None, max_length=20)
    complement: Optional[str] = Field(None, max_length=100)
    neighborhood: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=2)

class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    document: Optional[str] = Field(None, max_length=20)
    type_id: Optional[int] = None
    is_active: Optional[bool] = None
    working_hours: Optional[dict] = None
    max_simultaneous_appointments: Optional[int] = None
    allow_discount: Optional[bool] = None
    max_discount_percentage: Optional[float] = None
    feature_flags: Optional[dict] = None
    cep: Optional[str] = Field(None, max_length=10)
    street: Optional[str] = Field(None, max_length=150)
    number: Optional[str] = Field(None, max_length=20)
    complement: Optional[str] = Field(None, max_length=100)
    neighborhood: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=2)

class TenantTypeResponse(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True
        
class TenantResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: str
    document: Optional[str] = None
    is_active: bool
    onboarding_step: str
    created_at: datetime
    type: TenantTypeResponse
    subscription: Optional[SubscriptionResponse] = None
    working_hours: Optional[dict] = None
    max_simultaneous_appointments: Optional[int] = None
    allow_discount: bool
    max_discount_percentage: float
    feature_flags: dict = Field(default_factory=dict)
    cep: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

    class Config:
        from_attributes = True


class TenantUserCreate(BaseModel):
    name: str = Field(..., max_length=100)
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., max_length=100)
    role: str = Field("employee", max_length=20)
    permissions: Optional[list[str]] = None


class TenantUserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    permissions: Optional[list[str]] = None


class TenantUserUpdatePermissions(BaseModel):
    permissions: list[str] = Field(default_factory=list)

