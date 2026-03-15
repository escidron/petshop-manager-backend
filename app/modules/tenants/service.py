from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.plans.repository import PlanRepository
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.tenants.schemas import TenantCreate, TenantUpdate

from .repository import TenantRepository, TenantTypeRepository, TenantUserRepository

class TenantService:
    def __init__(self):
        self.repository = TenantRepository()
        self.type_repository = TenantTypeRepository()
        self.tenant_users_repository = TenantUserRepository()
        self.plan_repository = PlanRepository()
        self.subscription_repository = SubscriptionRepository()

    def create_tenant(
        self,
        db: Session,
        data: TenantCreate,
        user_id: int,
    ):
        # 1️⃣ Validar Tenant Type
        tenant_type = self.type_repository.get_by_id(db, data.type_id)
        if not tenant_type:
            raise HTTPException(
                status_code=400,
                detail="Invalid tenant type",
            )

        # 2️⃣ Criar Tenant
        tenant = self.repository.create(db, data)

        # 3️⃣ Criar vínculo owner
        self.tenant_users_repository.create(
            db=db,
            tenant_id=tenant.id,
            user_id=user_id,
            role="owner",
        )

        # 4️⃣ Buscar Plan
        plan = self.plan_repository.get_by_code(db, data.plan_code)
        if not plan:
            raise HTTPException(
                status_code=400,
                detail="Invalid plan",
            )

        now = datetime.now()

        # 5️⃣ Criar Subscription
        if plan.trial_days > 0:
            trial_end = now + timedelta(days=plan.trial_days)

            self.subscription_repository.create(
                db=db,
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="trialing",
                trial_ends_at=trial_end,
                current_period_end=trial_end,
            )
        else:
            period_end = now + timedelta(days=30)

            self.subscription_repository.create(
                db=db,
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="active",
                current_period_end=period_end,
            )

        return tenant
    
    def get_tenant(self, db: Session, tenant_id: int):
        tenant = self.repository.get_by_id(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def list_tenants(self, db: Session):
        return self.repository.list(db)

    def update_tenant(
        self,
        db: Session,
        tenant_id: int,
        data: TenantUpdate,
    ):
        tenant = self.get_tenant(db, tenant_id)

        if data.type_id:
            tenant_type = self.type_repository.get_by_id(
                db, data.type_id
            )
            if not tenant_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid tenant type",
                )

        return self.repository.update(db, tenant, data)

    def delete_tenant(self, db: Session, tenant_id: int):
        tenant = self.get_tenant(db, tenant_id)
        self.repository.delete(db, tenant)

    def update_subscription(
        self,
        db: Session,
        tenant_id: int,
        data,
    ):
        subscription = self.subscription_repository.get_active_by_tenant(db, tenant_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )
        return self.subscription_repository.update(
            db,
            subscription,
            {"payment_method": data.payment_method},
        )
