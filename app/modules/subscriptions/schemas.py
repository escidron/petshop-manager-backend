from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.modules.plans.schemas import PlanResponse


class BillingAddressSchema(BaseModel):
    country: str = "BR"
    state: str
    city: str
    zip_code: str
    line_1: str
    line_2: Optional[str] = None


class CheckoutRequest(BaseModel):
    plan_code: str
    payment_method: str = "credit_card"  # "credit_card" | "pix"
    card_token: Optional[str] = None     # obrigatório se payment_method == "credit_card"
    document: Optional[str] = None       # CPF ou CNPJ do titular
    billing_address: Optional[BillingAddressSchema] = None


class CheckoutResponse(BaseModel):
    pagarme_subscription_id: str
    status: str
    pix_qr_code: Optional[str] = None
    pix_qr_code_url: Optional[str] = None
    expires_at: Optional[str] = None


class SetupIntentResponse(BaseModel):
    client_secret: str


class PaymentMethodResponse(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool


class AddPaymentMethodRequest(BaseModel):
    card_token: str
    billing_address: Optional[BillingAddressSchema] = None
    document: Optional[str] = None


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
    pagarme_subscription_id: Optional[str] = None
    plan: PlanResponse

    class Config:
        from_attributes = True
