"""Construtor do BillingSnapshot a partir dos modelos de dados do Data Pet."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.subscriptions.models import Subscription, SubscriptionCharge, TenantCard
from app.modules.subscriptions.engine.types import (
    BillingSnapshot,
    LifecycleState,
    TrialState,
    BillingState,
    PaymentMethodState,
    PaymentMethodType,
    ProviderState,
    AddonState,
    OutstandingState,
)


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_billing_snapshot(
    subscription: Subscription,
    db: Optional[Session] = None,
    now_utc: Optional[datetime] = None,
) -> BillingSnapshot:
    """Constrói o snapshot imutável do faturamento de um tenant."""
    now = now_utc or datetime.now(timezone.utc)
    now = _normalize_dt(now)

    # 1. Trial State
    trial_ends = _normalize_dt(subscription.trial_ends_at)
    trial_starts = _normalize_dt(subscription.started_at)
    
    trial_active = bool(
        subscription.status == "trialing"
        and trial_ends is not None
        and trial_ends > now
    )
    seconds_remaining = (trial_ends - now).total_seconds() if trial_ends else 0.0

    trial_state = TrialState(
        is_active=trial_active,
        starts_at=trial_starts,
        ends_at=trial_ends,
        seconds_remaining=max(0.0, seconds_remaining),
    )

    # 2. Lifecycle State
    if subscription.status == "trialing":
        lifecycle = LifecycleState.TRIAL
    elif subscription.status == "active":
        lifecycle = LifecycleState.ACTIVE
    elif subscription.status == "past_due":
        lifecycle = LifecycleState.PAST_DUE
    elif subscription.status in ("canceled", "unpaid"):
        lifecycle = LifecycleState.CANCELED
    elif subscription.status == "incomplete":
        lifecycle = LifecycleState.INCOMPLETE
    else:
        lifecycle = LifecycleState.ACTIVE

    # 3. Billing Period State
    period_start = _normalize_dt(subscription.started_at)
    period_end = _normalize_dt(subscription.current_period_end)
    is_paid = bool(
        lifecycle == LifecycleState.ACTIVE
        or (lifecycle == LifecycleState.TRIAL and trial_active)
    )
    anchor_day = subscription.billing_day or (trial_ends.day if trial_ends else 1)

    billing_state = BillingState(
        anchor_day=anchor_day,
        current_period_start=period_start,
        current_period_end=period_end,
        is_current_period_paid=is_paid,
    )

    # 4. Payment Method & Cards
    default_card_id = None
    if db is not None:
        default_card = (
            db.query(TenantCard)
            .filter(TenantCard.tenant_id == subscription.tenant_id, TenantCard.is_default == True)
            .first()
        )
        if default_card:
            default_card_id = default_card.pagarme_card_id

    pm_str = (subscription.payment_method or "card").lower()
    pm_type = PaymentMethodType.CARD if pm_str == "card" else PaymentMethodType.PIX

    pm_state = PaymentMethodState(
        type=pm_type,
        default_card_id=default_card_id,
        has_valid_card=bool(default_card_id),
    )

    # 5. Provider & Charges State
    last_charge_id = None
    last_charge_status = None
    pending_pix_charge = None

    if db is not None:
        recent_charges = (
            db.query(SubscriptionCharge)
            .filter(SubscriptionCharge.subscription_id == subscription.id)
            .order_by(SubscriptionCharge.created_at.desc())
            .all()
        )
        if recent_charges:
            last_charge_id = recent_charges[0].pagarme_charge_id
            last_charge_status = recent_charges[0].status.lower()

        for c in recent_charges:
            if c.payment_method == "pix" and c.status.lower() in ("pending", "waiting_payment"):
                pending_pix_charge = c
                break

    # Se estiver em trial e tiver pagarme_subscription_id, trata-se de subscrição futura
    future_sub_id = None
    active_sub_id = None
    if subscription.pagarme_subscription_id:
        if lifecycle == LifecycleState.TRIAL:
            future_sub_id = subscription.pagarme_subscription_id
        else:
            active_sub_id = subscription.pagarme_subscription_id

    provider_state = ProviderState(
        active_subscription_id=active_sub_id,
        future_subscription_id=future_sub_id,
        future_subscription_start_at=trial_ends if future_sub_id else None,
        last_charge_id=last_charge_id,
        last_charge_status=last_charge_status,
    )

    # 6. Addons State
    addons = []
    if subscription.whatsapp_package_id:
        addons.append(
            AddonState(
                code=subscription.whatsapp_package_id,
                status=subscription.whatsapp_package_status or "inactive",
                paid_until=_normalize_dt(subscription.whatsapp_period_end) or period_end,
                messages_limit=subscription.whatsapp_messages_limit or 0,
                messages_used=subscription.whatsapp_messages_used or 0,
                cancel_at_period_end=False,
            )
        )

    # 7. Outstanding State
    outstanding_state = OutstandingState(
        has_pending_pix=bool(pending_pix_charge),
        pending_pix_charge_id=pending_pix_charge.pagarme_charge_id if pending_pix_charge else None,
        pending_pix_amount=pending_pix_charge.amount if pending_pix_charge else 0,
        has_failed_payment=bool(last_charge_status in ("failed", "payment_failed")),
    )

    return BillingSnapshot(
        tenant_id=subscription.tenant_id,
        snapshot_at=now,
        lifecycle=lifecycle,
        trial=trial_state,
        billing=billing_state,
        payment_method=pm_state,
        provider=provider_state,
        addons=addons,
        outstanding=outstanding_state,
    )
