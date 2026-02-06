from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.tenants.schemas import TenantCreate, TenantUpdate

from .repository import TenantRepository, TenantTypeRepository, TenantUserRepository


class TenantService:
    def __init__(self):
        self.repository = TenantRepository()
        self.type_repository = TenantTypeRepository()
        self.tenant_users_repository = TenantUserRepository()

    def create_tenant(self, db: Session, data: TenantCreate, user_id: int):
        tenant_type = self.type_repository.get_by_id(
            db, data.type_id
        )
        if not tenant_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant type",
            )
        tenant = self.repository.create(db, data)
        self.tenant_users_repository.create(
            db,
            tenant_id=tenant.id,
            user_id=user_id,
            role="owner",
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
