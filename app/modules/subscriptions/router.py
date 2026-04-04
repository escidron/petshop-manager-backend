from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_owner
from app.modules.subscriptions import service
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.subscriptions.schemas import (
    AddPaymentMethodRequest,
    CheckoutRequest,
    CheckoutResponse,
    PaymentMethodResponse,
    SubscriptionResponse,
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
        body.plan_code,
        card_token=body.card_token,
        payment_method=body.payment_method,
        document=body.document,
        billing_address=body.billing_address.model_dump() if body.billing_address else None,
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

    return sub


@router.post("/cancel", response_model=SubscriptionResponse)
def cancel(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    return service.cancel_subscription(db, tenant)


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


@router.delete("/payment-methods/{pm_id}", status_code=204)
def remove_payment_method(
    pm_id: str,
    ctx: dict = Depends(require_owner),
):
    service.detach_payment_method(ctx["tenant"], pm_id)
