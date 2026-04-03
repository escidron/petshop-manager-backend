from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_owner
from app.modules.subscriptions import service
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.subscriptions.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentMethodResponse,
    SetupIntentResponse,
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
    """Inicia o fluxo de assinatura. Retorna client_secret para o Stripe Elements confirmar."""
    tenant = ctx["tenant"]
    user = ctx["user"]
    return service.create_checkout(db, tenant, user.email, body.plan_code)


@router.get("/mine", response_model=SubscriptionResponse)
def get_my_subscription(
    ctx: dict = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sem assinatura ativa")
    return sub


@router.post("/cancel", response_model=SubscriptionResponse)
def cancel(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = ctx["tenant"]
    return service.cancel_subscription(db, tenant)


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
def get_payment_methods(
    ctx: dict = Depends(get_current_tenant),
):
    tenant = ctx["tenant"]
    return service.list_payment_methods(tenant)


@router.post("/payment-methods/setup", response_model=SetupIntentResponse)
def setup_payment_method(
    ctx: dict = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Cria um SetupIntent para adicionar cartão sem cobrar nada."""
    tenant = ctx["tenant"]
    user = ctx["user"]
    client_secret = service.create_setup_intent(tenant, user.email, db)
    return {"client_secret": client_secret}


@router.post("/payment-methods/{pm_id}/default", status_code=204)
def set_default(
    pm_id: str,
    ctx: dict = Depends(require_owner),
):
    service.set_default_payment_method(ctx["tenant"], pm_id)


@router.delete("/payment-methods/{pm_id}", status_code=204)
def remove_payment_method(
    pm_id: str,
    ctx: dict = Depends(require_owner),
):
    service.detach_payment_method(ctx["tenant"], pm_id)
