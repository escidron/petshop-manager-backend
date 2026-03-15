from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.modules.subscriptions.schemas import SubscriptionResponse


class TenantBase(BaseModel):
    name: str
    type_id: int = 1
    is_active: bool = True
    phone:str
    plan_code: str
    onboarding_step: str = "services"

class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    type_id: Optional[int] = None
    is_active: Optional[bool] = None

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
    phone: str
    is_active: bool
    onboarding_step: str
    created_at: datetime
    type: TenantTypeResponse
    subscription: Optional[SubscriptionResponse] = None

    class Config:
        from_attributes = True

