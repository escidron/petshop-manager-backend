from typing import Optional

from sqlalchemy.orm import Session

from app.modules.auth.token import (
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.modules.users.models import User


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

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    payload = {
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role,
    }

    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "user": {
            "id": str(user.id),
            "role": user.role,
            "tenant_id": str(user.tenant_id),
        },
    }
