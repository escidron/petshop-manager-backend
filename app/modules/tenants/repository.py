from sqlalchemy.orm import Session
from app.modules.tenants.models import Tenant, TenantType
from app.modules.tenants.schemas import TenantCreate, TenantUpdate


class TenantRepository:
    def create(self, db: Session, data: TenantCreate) -> Tenant:
        tenant = Tenant(**data.model_dump())
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
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
