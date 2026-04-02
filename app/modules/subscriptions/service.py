from datetime import datetime, timezone, timedelta

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.modules.plans.models import Plan
from app.modules.subscriptions.models import Subscription
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.tenants.models import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY

_repo = SubscriptionRepository()


def _ensure_stripe_customer(db: Session, tenant: Tenant, user_email: str) -> str:
    """Create Stripe Customer for the tenant if not yet created. Returns customer id."""
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    customer = stripe.Customer.create(
        email=user_email,
        name=tenant.name,
        metadata={"tenant_id": str(tenant.id)},
    )

    tenant.stripe_customer_id = customer.id
    db.add(tenant)
    db.flush()

    return customer.id


def create_checkout(
    db: Session,
    tenant: Tenant,
    user_email: str,
    plan_code: str,
) -> dict:
    plan: Plan | None = db.query(Plan).filter(Plan.code == plan_code, Plan.is_active == True).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    # Free trial: no Stripe payment needed
    if plan_code == "FREE_TRIAL":
        trial_ends_at = datetime.now(timezone.utc) + timedelta(days=plan.trial_days or 14)
        _repo.create(
            db=db,
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="trialing",
            current_period_end=trial_ends_at,
            trial_ends_at=trial_ends_at,
        )
        db.commit()
        return {"status": "trialing", "trial_ends_at": trial_ends_at.isoformat()}

    if not plan.stripe_price_id:
        raise HTTPException(
            status_code=422,
            detail="Este plano ainda não possui um Price configurado no Stripe",
        )

    customer_id = _ensure_stripe_customer(db, tenant, user_email)

    stripe_sub = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": plan.stripe_price_id}],
        payment_behavior="default_incomplete",
        payment_settings={"save_default_payment_method": "on_subscription"},
        expand=["latest_invoice.payments"],
    )

    # current_period_end may be absent on incomplete subscriptions
    raw_period_end = getattr(stripe_sub, "current_period_end", None)
    period_end = (
        datetime.fromtimestamp(raw_period_end, tz=timezone.utc)
        if raw_period_end
        else datetime.now(timezone.utc) + timedelta(days=30)
    )

    existing = _repo.get_active_by_tenant(db, tenant.id)
    if existing:
        _repo.update(
            db,
            existing,
            {
                "plan_id": plan.id,
                "status": "incomplete",
                "stripe_subscription_id": stripe_sub["id"],
                "current_period_end": period_end,
                "trial_ends_at": None,
                "canceled_at": None,
            },
        )
    else:
        _repo.create(
            db=db,
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="incomplete",
            current_period_end=period_end,
            stripe_subscription_id=stripe_sub["id"],
        )
        db.commit()

    payments = stripe_sub["latest_invoice"]["payments"]["data"]
    payment_intent_id = payments[0]["payment_intent"]
    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

    return {
        "client_secret": payment_intent["client_secret"],
        "stripe_subscription_id": stripe_sub["id"],
    }


def cancel_subscription(db: Session, tenant: Tenant) -> Subscription:
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    if sub.stripe_subscription_id:
        stripe.Subscription.cancel(sub.stripe_subscription_id)

    return _repo.update(
        db,
        sub,
        {"status": "canceled", "canceled_at": datetime.now(timezone.utc)},
    )


def list_payment_methods(tenant: Tenant) -> list[dict]:
    if not tenant.stripe_customer_id:
        return []

    customer = stripe.Customer.retrieve(tenant.stripe_customer_id)
    default_pm = customer.get("invoice_settings", {}).get("default_payment_method")

    pms = stripe.PaymentMethod.list(
        customer=tenant.stripe_customer_id,
        type="card",
    )

    result = []
    for pm in pms.data:
        card = pm.card
        result.append(
            {
                "id": pm.id,
                "brand": card.brand,
                "last4": card.last4,
                "exp_month": card.exp_month,
                "exp_year": card.exp_year,
                "is_default": pm.id == default_pm,
            }
        )

    return result


def create_setup_intent(tenant: Tenant, user_email: str, db: Session) -> str:
    customer_id = _ensure_stripe_customer(db, tenant, user_email)
    db.commit()

    setup_intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"],
        usage="off_session",
    )

    return setup_intent.client_secret


def handle_webhook_event(payload: bytes, sig_header: str) -> None:
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Assinatura do webhook inválida")

    from app.config.database import SessionLocal

    db = SessionLocal()
    try:
        event_type = event["type"]

        if event_type == "invoice.payment_succeeded":
            _on_invoice_paid(db, event["data"]["object"])

        elif event_type == "invoice.payment_failed":
            _on_invoice_failed(db, event["data"]["object"])

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            _on_subscription_updated(db, event["data"]["object"])

    finally:
        db.close()


def _on_invoice_paid(db: Session, invoice: dict) -> None:
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    period_end = datetime.fromtimestamp(stripe_sub["current_period_end"], tz=timezone.utc)

    sub = _repo.get_by_stripe_subscription_id(db, stripe_sub_id)
    if sub:
        _repo.update(db, sub, {"status": "active", "current_period_end": period_end})


def _on_invoice_failed(db: Session, invoice: dict) -> None:
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    sub = _repo.get_by_stripe_subscription_id(db, stripe_sub_id)
    if sub:
        _repo.update(db, sub, {"status": "past_due"})


def _on_subscription_updated(db: Session, stripe_sub: dict) -> None:
    sub = _repo.get_by_stripe_subscription_id(db, stripe_sub["id"])
    if not sub:
        return

    period_end = datetime.fromtimestamp(stripe_sub["current_period_end"], tz=timezone.utc)
    status = stripe_sub["status"]

    canceled_at = None
    if stripe_sub.get("canceled_at"):
        canceled_at = datetime.fromtimestamp(stripe_sub["canceled_at"], tz=timezone.utc)

    _repo.update(
        db,
        sub,
        {
            "status": status,
            "current_period_end": period_end,
            "canceled_at": canceled_at,
        },
    )
