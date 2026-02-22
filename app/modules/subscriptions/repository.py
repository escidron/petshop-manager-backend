from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.subscriptions.models import Subscription


class SubscriptionRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        plan_id: int,
        status: str,
        current_period_end: datetime,
        trial_ends_at: datetime | None = None,
    ):
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_end=current_period_end,
        )

        db.add(subscription)
        db.flush()

        return subscription