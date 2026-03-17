from sqlalchemy.orm import Session
from app.modules.tenants.models import Tenant, TenantType
from app.modules.tenants.schemas import TenantCreate, TenantUpdate
from app.modules.users.models import TenantUser


class TenantRepository:
    def create(self, db: Session, data: TenantCreate) -> Tenant:
        tenant_data = data.model_dump(exclude={"plan_code"})
        tenant = Tenant(**tenant_data)

        db.add(tenant)
        db.flush()

        return tenant

    def get_by_id(self, db: Session, tenant_id: int) -> Tenant | None:
        return db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def list(self, db: Session) -> list[Tenant]:
        return db.query(Tenant).order_by(Tenant.name).all()

    def update(
        self,
        db: Session,
        tenant: Tenant,
        data: TenantUpdate,
    ) -> Tenant:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tenant, field, value)

        db.commit()
        db.refresh(tenant)
        return tenant

    def delete(self, db: Session, tenant: Tenant):
        db.delete(tenant)
        db.commit()


class TenantTypeRepository:
    def get_by_id(self, db: Session, type_id: int) -> TenantType | None:
        return (
            db.query(TenantType)
            .filter(
                TenantType.id == type_id,
                TenantType.is_active,
            )
            .first()
        )

class TenantUserRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        user_id: int,
        role: str,
    ):
        tenant_user = TenantUser(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
        )
        db.add(tenant_user)
        db.commit()
        db.refresh(tenant_user)
        return tenant_user

    def list_by_tenant(self, db: Session, tenant_id: int):
        from app.modules.users.models import User
        return (
            db.query(TenantUser, User)
            .join(User, User.id == TenantUser.user_id)
            .filter(TenantUser.tenant_id == tenant_id, TenantUser.active == True)
            .all()
        )

    def get_by_user_and_tenant(self, db: Session, user_id: int, tenant_id: int):
        return (
            db.query(TenantUser)
            .filter(TenantUser.user_id == user_id, TenantUser.tenant_id == tenant_id)
            .first()
        )

    def soft_delete(self, db: Session, user_id: int, tenant_id: int) -> bool:
        from app.modules.users.models import User
        tenant_user = self.get_by_user_and_tenant(db, user_id, tenant_id)
        if not tenant_user:
            return False
        tenant_user.active = False
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_active = False
        db.commit()
        return True