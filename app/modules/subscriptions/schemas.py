from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.modules.plans.schemas import PlanResponse


class CheckoutRequest(BaseModel):
    plan_code: str


class CheckoutResponse(BaseModel):
    client_secret: str
    stripe_subscription_id: str


class SetupIntentResponse(BaseModel):
    client_secret: str


class PaymentMethodResponse(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool


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
    stripe_subscription_id: Optional[str] = None
    plan: PlanResponse

    class Config:
        from_attributes = True
