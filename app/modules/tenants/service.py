from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.plans.repository import PlanRepository
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.tenants.schemas import TenantCreate, TenantUpdate, TenantUserCreate
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService

from .repository import TenantRepository, TenantTypeRepository, TenantUserRepository

class TenantService:
    def __init__(self):
        self.repository = TenantRepository()
        self.type_repository = TenantTypeRepository()
        self.tenant_users_repository = TenantUserRepository()
        self.plan_repository = PlanRepository()
        self.subscription_repository = SubscriptionRepository()
        self.user_service = UserService()

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
                detail="Tipo de empresa inválido",
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
                detail="Plano inválido",
            )

        now = datetime.now(timezone.utc)

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
            # Plano pago sem trial: cria como "incomplete" até o pagamento ser confirmado via webhook
            period_end = now + timedelta(days=30)

            self.subscription_repository.create(
                db=db,
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="incomplete",
                current_period_end=period_end,
            )

        return tenant
    
    def get_tenant(self, db: Session, tenant_id: int):
        tenant = self.repository.get_by_id(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada",
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
                    detail="Tipo de empresa inválido",
                )

        return self.repository.update(db, tenant, data)

    def delete_tenant(self, db: Session, tenant_id: int):
        tenant = self.get_tenant(db, tenant_id)
        self.repository.delete(db, tenant)

    def list_tenant_users(self, db: Session, tenant_id: int):
        results = self.tenant_users_repository.list_by_tenant(db, tenant_id)
        return [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": tenant_user.role,
                "is_active": user.is_active,
            }
            for tenant_user, user in results
        ]

    def create_tenant_user(self, db: Session, tenant_id: int, data: TenantUserCreate):
        existing = db.query(User).filter(User.email == data.email).first()

        if existing:
            if existing.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="E-mail já cadastrado",
                )
            # Reactivate previously deleted user
            existing.is_active = True
            existing.name = data.name
            existing.role = data.role

            tenant_user = self.tenant_users_repository.get_by_user_and_tenant(
                db, existing.id, tenant_id
            )
            if tenant_user:
                tenant_user.active = True
                tenant_user.role = data.role
            else:
                self.tenant_users_repository.create(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=existing.id,
                    role=data.role,
                )

            db.commit()
            db.refresh(existing)
            return {
                "id": existing.id,
                "name": existing.name,
                "email": existing.email,
                "role": data.role,
                "is_active": existing.is_active,
            }

        user_create = UserCreate(
            name=data.name,
            email=data.email,
            password=data.password,
            role=data.role,
        )
        user = self.user_service.create(db, user_create)

        self.tenant_users_repository.create(
            db=db,
            tenant_id=tenant_id,
            user_id=user.id,
            role=data.role,
        )

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": data.role,
            "is_active": user.is_active,
        }

    def remove_tenant_user(
        self,
        db: Session,
        tenant_id: int,
        user_id: int,
        requesting_user_id: int,
    ):
        if user_id == requesting_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Você não pode se remover",
            )
        removed = self.tenant_users_repository.soft_delete(db, user_id, tenant_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado nesta empresa",
            )

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
                detail="Assinatura não encontrada",
            )
        return self.subscription_repository.update(
            db,
            subscription,
            {"payment_method": data.payment_method},
        )
