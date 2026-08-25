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
    card_token: Optional[str] = None     # obrigatório se payment_method == "credit_card" e card_id não fornecido
    card_id: Optional[str] = None        # opcional se card_token fornecido
    document: Optional[str] = None       # CPF ou CNPJ do titular
    billing_address: Optional[BillingAddressSchema] = None
    start_at: Optional[str] = None       # ISO 8601 — para migrar de PIX para cartão sem sobreposição
    idempotency_key: Optional[str] = None


class SubscriptionChargeResponse(BaseModel):
    id: str
    amount: int
    status: str
    payment_method: str
    card_brand: Optional[str] = None
    card_last_four: Optional[str] = None
    pix_qr_code: Optional[str] = None
    pix_qr_code_url: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class UpdateChargeCardRequest(BaseModel):
    card_token: str
    billing_address: Optional[BillingAddressSchema] = None
    document: Optional[str] = None


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


class ProrationPreviewRequest(BaseModel):
    package_code: str


class ProrationPreviewResponse(BaseModel):
    package_code: str
    package_name: str
    monthly_price_cents: int
    prorated_price_cents: int
    prorated_messages: Optional[int] = None
    total_messages: Optional[int] = None
    billing_day: int
    days_remaining: int
    total_days_in_cycle: int
    next_billing_date: str
    is_prorated: bool


class HirePackageRequest(BaseModel):
    package_code: str
    payment_method: str = "credit_card"  # "credit_card" | "pix"
    card_token: Optional[str] = None
    card_id: Optional[str] = None
    document: Optional[str] = None
    billing_address: Optional[BillingAddressSchema] = None
    idempotency_key: Optional[str] = None


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
    eligible_for_refund: Optional[bool] = False

    # WhatsApp Add-on Package Tracking
    whatsapp_package_id: Optional[str] = None
    whatsapp_package_status: Optional[str] = "inactive"
    whatsapp_messages_limit: Optional[int] = 0
    whatsapp_messages_used: Optional[int] = 0
    whatsapp_period_end: Optional[datetime] = None
    pagarme_whatsapp_subscription_id: Optional[str] = None
    billing_day: Optional[int] = 1

    class Config:
        from_attributes = True
