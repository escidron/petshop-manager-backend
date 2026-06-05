from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.auth.token import (
    verify_password,
    create_access_token,
    create_refresh_token,
    create_selection_token,
)
from app.modules.plans.repository import PlanRepository
from app.modules.tenants.service import TenantService
from app.modules.users.models import TenantUser, User
from app.modules.users.service import UserService
from app.modules.auth.models import PasswordResetOTP
from app.services.email.service import EmailService
import secrets
import string
from datetime import datetime, timedelta


class AuthService:
    def __init__(self):
        self.user_service = UserService()
        self.tenant_service = TenantService()
        self.plan_repository = PlanRepository()
        self.email_service = EmailService()

    def signup(self, db: Session, user_data, tenant_data):

        try:
            # 1️⃣ Verificar email
            existing = db.query(User).filter(
                User.email == user_data.email
            ).first()

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="E-mail já cadastrado"
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

            # 5️⃣ Enviar email de boas-vindas (Assíncrono seria ideal, mas por ora direto)
            try:
                self.email_service.send_welcome_email(
                    to_email=user.email,
                    user_name=user.name
                )
            except Exception as e:
                print(f"Error sending welcome email: {e}")

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

    def forgot_password(self, db: Session, email: str, base_url: str):
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="E-mail não cadastrado.")

        # Gerar OTP de 6 dígitos
        otp_code = "".join(secrets.choice(string.digits) for _ in range(6))
        
        # Limpar OTPs antigos do usuário
        db.query(PasswordResetOTP).filter(PasswordResetOTP.user_id == user.id).delete()
        
        # Salvar novo OTP (expira em 15 minutos)
        new_otp = PasswordResetOTP(
            user_id=user.id,
            otp_code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=15)
        )
        db.add(new_otp)
        db.commit()

        # Enviar e-mail com o código
        self.email_service.send_password_reset_email(
            to_email=user.email,
            user_name=user.name,
            otp_code=otp_code
        )
        return True

    def verify_otp(self, db: Session, email: str, otp_code: str):
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=400, detail="E-mail ou código inválido")

        otp_record = db.query(PasswordResetOTP).filter(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.otp_code == otp_code
        ).first()

        if not otp_record or otp_record.is_expired:
            raise HTTPException(status_code=400, detail="Código inválido ou expirado")

        return True

    def reset_password(self, db: Session, email: str, otp_code: str, new_password: str):
        from app.modules.auth.token import hash_password
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        # Verificar OTP novamente antes de resetar
        self.verify_otp(db, email, otp_code)

        # Atualizar senha
        user.password = hash_password(new_password)
        
        # Consumir o OTP
        db.query(PasswordResetOTP).filter(PasswordResetOTP.user_id == user.id).delete()
        
        db.commit()
        return True


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> Optional[dict]:
    """
    Valida credenciais e retorna tokens ou sinaliza seleção de tenant.
    """
    user: User | None = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )
    if not user:
        return None

    if not verify_password(password, user.password):
        return None

    tenant_users = (
        db.query(TenantUser)
        .filter(TenantUser.user_id == user.id, TenantUser.active == True)
        .all()
    )

    if not tenant_users:
        return None

    if len(tenant_users) > 1:
        from app.modules.tenants.models import Tenant
        tenants = []
        for tu in tenant_users:
            t = db.query(Tenant).filter(Tenant.id == tu.tenant_id, Tenant.is_active == True).first()
            if t:
                tenants.append({"id": t.id, "name": t.name})

        return {
            "needs_tenant_selection": True,
            "selection_token": create_selection_token(user.id),
            "tenants": tenants,
        }

    tenant = tenant_users[0]
    payload = {
        "user_id": str(user.id),
        "tenant_id": str(tenant.tenant_id),
        "role": tenant.role,
    }

    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "user": {
            "id": str(user.id),
            "role": tenant.role,
            "tenant_id": str(tenant.tenant_id),
            "name": user.name,
        },
    }
