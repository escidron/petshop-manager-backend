from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.auth.token import (
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.modules.plans.repository import PlanRepository
from app.modules.tenants.service import TenantService
from app.modules.users.models import TenantUser, User
from app.modules.users.service import UserService


class AuthService:
    def __init__(self):
        self.user_service = UserService()
        self.tenant_service = TenantService()
        self.plan_repository = PlanRepository()

    def signup(self, db: Session, user_data, tenant_data):

        try:
            # 1️⃣ Verificar email
            existing = db.query(User).filter(
                User.email == user_data.email
            ).first()

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Email already registered"
                )

            # 2️⃣ Criar user (SEM COMMIT)
            user = self.user_service.create(db, user_data)

            # 3️⃣ Criar tenant + subscription (SEM COMMIT)
            result = self.tenant_service.create_tenant(
                db=db,
                data=tenant_data,
                user_id=user.id,
            )

            # 4️⃣ Commit único
            db.commit()

        except Exception:
            db.rollback()
            raise

        # 5️⃣ Criar token depois do commit
        print('resultsss', result)
        token_data = {
            "user_id": str(user.id),
            "tenant_id": str(result.id),
            "role": "owner",
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user.id),
                "role": "owner",
                "tenant_id": str(result.id),
            },
        }


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> Optional[dict]:
    """
    Valida credenciais e retorna tokens se estiver ok.
    """
    user: User | None = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )
    # handle user having multiple tenants
    tenant: TenantUser | None = (
        db.query(TenantUser)
        .filter(TenantUser.user_id == user.id)
        .first()
    )
    if not user:
        return None

    if not verify_password(password, user.password):
        return None

    payload = {
        "user_id": str(user.id),
        "tenant_id": str(tenant.tenant_id),
        "role": user.role,
    }

    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "user": {
            "id": str(user.id),
            "role": user.role,
            "tenant_id": str(tenant.tenant_id),
            "name": user.name,
        },
    }
