from datetime import datetime, timedelta, timezone

from app.modules.auth.token import verify_password

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
        print(f"[DEBUG CREATE_TENANT] Starting create_tenant for user_id={user_id}. Data: {data.model_dump()}")
        try:
            # 1️⃣ Validar Tenant Type
            tenant_type = self.type_repository.get_by_id(db, data.type_id)
            if not tenant_type:
                print(f"[DEBUG CREATE_TENANT] Invalid tenant type: {data.type_id}")
                raise HTTPException(
                    status_code=400,
                    detail="Tipo de empresa inválido",
                )

            # 2️⃣ Criar Tenant
            tenant = self.repository.create(db, data)
            print(f"[DEBUG CREATE_TENANT] Tenant created in memory. ID={tenant.id}")

            # 3️⃣ Atualizar o tenant_id da sessão para o novo tenant (necessário para passar no RLS)
            from sqlalchemy import text
            print(f"[DEBUG CREATE_TENANT] Setting SET LOCAL app.current_tenant_id = {tenant.id}")
            db.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tenant.id})

            # 4️⃣ Criar vínculo owner
            print(f"[DEBUG CREATE_TENANT] Creating tenant_user owner link for user_id={user_id}")
            self.tenant_users_repository.create(
                db=db,
                tenant_id=tenant.id,
                user_id=user_id,
                role="owner",
            )

            # 5️⃣ Buscar Plan
            print(f"[DEBUG CREATE_TENANT] Fetching plan for code: {data.plan_code}")
            plan = self.plan_repository.get_by_code(db, data.plan_code)
            if not plan:
                print(f"[DEBUG CREATE_TENANT] Plan not found for code: {data.plan_code}")
                raise HTTPException(
                    status_code=400,
                    detail="Plano inválido",
                )
            print(f"[DEBUG CREATE_TENANT] Plan found: {plan.name} (ID={plan.id})")

            now = datetime.now(timezone.utc)

            # 6️⃣ Criar Subscription
            if plan.trial_days > 0:
                trial_end = now + timedelta(days=plan.trial_days)
                print(f"[DEBUG CREATE_TENANT] Creating trialing subscription ending at {trial_end}")
                sub = self.subscription_repository.create(
                    db=db,
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    status="trialing",
                    trial_ends_at=trial_end,
                    current_period_end=trial_end,
                )
            else:
                period_end = now + timedelta(days=30)
                print(f"[DEBUG CREATE_TENANT] Creating incomplete subscription ending at {period_end}")
                sub = self.subscription_repository.create(
                    db=db,
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    status="incomplete",
                    current_period_end=period_end,
                )

            print("[DEBUG CREATE_TENANT] Committing transaction...")
            db.commit()
            tenant.subscription = sub
            print("[DEBUG CREATE_TENANT] Success! Tenant and subscription committed.")
            return tenant
        except Exception as e:
            print(f"[DEBUG CREATE_TENANT] ERROR occurred: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            raise
    
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

    def _perform_tenant_deletion(self, db: Session, tenant):
        from app.modules.subscriptions.models import Subscription, SubscriptionCharge
        from app.modules.users.models import TenantUser, User

        # Deletar as cobranças e assinaturas primeiro para evitar erro de FK
        db.query(SubscriptionCharge).filter(SubscriptionCharge.tenant_id == tenant.id).delete()
        db.query(Subscription).filter(Subscription.tenant_id == tenant.id).delete()
        db.flush()

        # Identificar todos os IDs de usuários vinculados a este tenant ANTES de deletar
        user_ids = [tu.user_id for tu in db.query(TenantUser).filter(TenantUser.tenant_id == tenant.id).all()]

        # Deletar o tenant (isso vai deletar os TenantUser via CASCADE e outros com CASCADE configurado)
        db.delete(tenant)
        db.flush()

        # Para cada usuário que estava no tenant, verificar se ficou órfão e deletar se necessário
        for uid in user_ids:
            other_tenants = db.query(TenantUser).filter(TenantUser.user_id == uid).count()
            if other_tenants == 0:
                db.query(User).filter(User.id == uid).delete()

    def delete_tenant(self, db: Session, tenant_id: int):
        tenant = self.get_tenant(db, tenant_id)
        self._perform_tenant_deletion(db, tenant)
        db.commit()

    def delete_own_tenant(self, db: Session, tenant, user) -> None:
        """Permanently deletes the tenant and all its data.
        Password verification must be done at the router level.
        Also cancels the Pagar.me subscription if active.
        """
        from app.modules.subscriptions import service as sub_service

        # Cancel Pagar.me subscription if it exists and isn't already canceled
        sub = self.subscription_repository.get_active_by_tenant(db, tenant.id)
        if sub and sub.status not in ("canceled", "trialing"):
            try:
                sub_service.cancel_subscription(db, tenant)
            except Exception:
                # Even if Pagar.me call fails, proceed with deletion
                pass

        self._perform_tenant_deletion(db, tenant)
        db.commit()

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

        db.commit()
        db.refresh(user)

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
