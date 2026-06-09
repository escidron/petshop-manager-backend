from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.subscriptions.models import Subscription, SubscriptionCharge


class SubscriptionRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        plan_id: int,
        status: str,
        current_period_end: datetime,
        trial_ends_at: datetime | None = None,
        pagarme_subscription_id: str | None = None,
    ) -> Subscription:
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_end=current_period_end,
            pagarme_subscription_id=pagarme_subscription_id,
        )

        db.add(subscription)
        db.flush()

        return subscription

    def get_active_by_tenant(self, db: Session, tenant_id: int) -> Subscription | None:
        return (
            db.query(Subscription)
            .filter(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.started_at.desc())
            .first()
        )

    def get_by_pagarme_subscription_id(
        self, db: Session, pagarme_subscription_id: str
    ) -> Subscription | None:
        return (
            db.query(Subscription)
            .filter(Subscription.pagarme_subscription_id == pagarme_subscription_id)
            .first()
        )

    def update(self, db: Session, subscription: Subscription, data: dict) -> Subscription:
        for key, value in data.items():
            setattr(subscription, key, value)

        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return subscription


class SubscriptionChargeRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        subscription_id: int,
        pagarme_charge_id: str,
        amount: int,
        status: str,
        payment_method: str,
        pix_qr_code: str | None = None,
        pix_qr_code_url: str | None = None,
        expires_at: datetime | None = None,
    ) -> SubscriptionCharge:
        charge = SubscriptionCharge(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            pagarme_charge_id=pagarme_charge_id,
            amount=amount,
            status=status,
            payment_method=payment_method,
            pix_qr_code=pix_qr_code,
            pix_qr_code_url=pix_qr_code_url,
            expires_at=expires_at,
        )
        db.add(charge)
        db.flush()
        return charge

    def get_by_pagarme_charge_id(self, db: Session, pagarme_charge_id: str) -> SubscriptionCharge | None:
        return (
            db.query(SubscriptionCharge)
            .filter(SubscriptionCharge.pagarme_charge_id == pagarme_charge_id)
            .first()
        )

    def list_by_tenant(self, db: Session, tenant_id: int) -> list[SubscriptionCharge]:
        return (
            db.query(SubscriptionCharge)
            .filter(SubscriptionCharge.tenant_id == tenant_id)
            .order_by(SubscriptionCharge.created_at.desc())
            .all()
        )

    def update(self, db: Session, charge: SubscriptionCharge, data: dict) -> SubscriptionCharge:
        for key, value in data.items():
            setattr(charge, key, value)
        db.add(charge)
        db.commit()
        db.refresh(charge)
        return charge

