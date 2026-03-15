from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.modules.plans.schemas import PlanResponse

class SubscriptionUpdate(BaseModel):
    payment_method: str

class SubscriptionResponse(BaseModel):
    id: int
    tenant_id: int
    plan_id: int
    status: str
    started_at: datetime
    trial_ends_at: Optional[datetime] = None
    current_period_end: datetime
    canceled_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    plan: PlanResponse

    class Config:
        from_attributes = True
