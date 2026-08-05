from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_owner
from app.modules.subscriptions import service
from app.modules.subscriptions.repository import SubscriptionRepository, SubscriptionChargeRepository
from app.modules.subscriptions.schemas import (
    AddPaymentMethodRequest,
    CheckoutRequest,
    PaymentMethodResponse,
    SubscriptionResponse,
    SubscriptionChargeResponse,
    UpdateChargeCardRequest,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
_repo = SubscriptionRepository()


@router.post("/checkout", response_model=dict)
def checkout(
    body: CheckoutRequest,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Inicia o fluxo de assinatura via Pagar.me."""
    tenant = ctx["tenant"]
    user = ctx["user"]
    return service.create_checkout(
        db,
        tenant,
        user.email,
        user.name,
        body.plan_code,
        card_token=body.card_token,
        card_id=body.card_id,
        payment_method=body.payment_method,
        document=body.document,
        billing_address=body.billing_address.model_dump() if body.billing_address else None,
        start_at=body.start_at,
        idempotency_key=body.idempotency_key,
    )



@router.get("/mine", response_model=SubscriptionResponse)
def get_my_subscription(
    ctx: dict = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    from datetime import datetime, timezone

    tenant = ctx["tenant"]
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Sem assinatura ativa")

    # Se o período expirou, marca como past_due para liberar novo pagamento
    # (em produção isso seria feito pelo webhook do Pagar.me)
    if sub.status in ("active", "pending") and sub.current_period_end:
        period_end = sub.current_period_end
        # Garante que period_end é timezone-aware para comparação segura
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end < datetime.now(timezone.utc):
            sub = _repo.update(db, sub, {"status": "past_due"})

    # Check if eligible for refund
    sub.eligible_for_refund = False
    charge_repo = SubscriptionChargeRepository()
    charge = charge_repo.get_first_paid_charge(db, sub.id)
    if charge:
        created_dt = charge.created_at
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        days_since_payment = (datetime.now(timezone.utc) - created_dt).days
        if days_since_payment <= 7:
            sub.eligible_for_refund = True

    return sub


@router.post("/cancel", response_model=SubscriptionResponse)
def cancel(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    return service.cancel_subscription(db, tenant)


@router.post("/refund-and-cancel", response_model=SubscriptionResponse)
def refund_and_cancel(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Estorna a cobrança mais recente (se dentro de 7 dias do 1º pagamento) e cancela a assinatura."""
    tenant = ctx["tenant"]
    return service.refund_and_cancel_subscription(db, tenant)


@router.post("/payment-methods", response_model=PaymentMethodResponse)
def add_payment_method(
    body: AddPaymentMethodRequest,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    user = ctx["user"]
    return service.add_payment_method(
        db,
        tenant,
        user.email,
        user.name,
        body.card_token,
        billing_address=body.billing_address.model_dump() if body.billing_address else None,
        document=body.document,
    )


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
def get_payment_methods(
    ctx: dict = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    return service.list_payment_methods(db, tenant)


@router.post("/payment-methods/{pm_id}/default", status_code=204)
def set_default(
    pm_id: str,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    service.set_default_payment_method(db, ctx["tenant"], pm_id)


@router.post("/change-to-pix", status_code=204)
def change_to_pix(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    service.change_subscription_to_pix(db, ctx["tenant"])


@router.delete("/payment-methods/{pm_id}", status_code=204)
def remove_payment_method(
    pm_id: str,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    service.detach_payment_method(db, ctx["tenant"], pm_id)


@router.get("/charges", response_model=list[SubscriptionChargeResponse])
def get_charges(
    ctx: dict = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Retorna o histórico de cobranças do tenant."""
    tenant = ctx["tenant"]
    return service.list_charges(db, tenant)


@router.patch("/charges/{charge_id}/card", response_model=dict)
def update_charge_card(
    charge_id: str,
    body: UpdateChargeCardRequest,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Atualiza o cartão de crédito associado a uma cobrança específica e tenta cobrar novamente."""
    tenant = ctx["tenant"]
    user = ctx["user"]
    return service.update_charge_card(
        db=db,
        tenant=tenant,
        user_email=user.email,
        user_name=user.name,
        charge_id=charge_id,
        card_token=body.card_token,
        billing_address=body.billing_address.model_dump() if body.billing_address else None,
        document=body.document,
    )


@router.post("/charges/{charge_id}/retry", response_model=dict)
def retry_charge(
    charge_id: str,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Retenta manualmente a cobrança falha no Pagar.me."""
    tenant = ctx["tenant"]
    return service.retry_charge(db, tenant, charge_id)


@router.post("/charges/{charge_id}/capture", response_model=dict)
def capture_charge(
    charge_id: str,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Captura uma cobrança que foi previamente pré-autorizada."""
    tenant = ctx["tenant"]
    return service.capture_charge(db, tenant, charge_id)


@router.post("/charges/{charge_id}/cancel", response_model=dict)
def cancel_charge(
    charge_id: str,
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Cancela/estorna uma cobrança no Pagar.me."""
    tenant = ctx["tenant"]
    return service.cancel_charge(db, tenant, charge_id)

