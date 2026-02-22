from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.token import decode_token
from app.modules.tenants.models import Tenant
from app.modules.users.models import TenantUser, User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401)

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401)

    user = db.query(User).filter(
        User.id == int(payload["user_id"])
    ).first()

    if not user:
        raise HTTPException(status_code=401)

    return user

def get_current_tenant(
    request: Request,
    db: Session = Depends(get_db),
):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_token(token)

    try:
        user_id = int(payload["user_id"])
        tenant_id = int(payload["tenant_id"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    tenant_user = (
        db.query(TenantUser)
        .filter(
            TenantUser.user_id == user_id,
            TenantUser.tenant_id == tenant_id,
        )
        .first()
    )

    if not tenant_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not linked to tenant",
        )

    user = db.query(User).filter(User.id == user_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not user or not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or tenant not found",
        )
    request.state.tenant_user = tenant_user

    return {
        "user": user,
        "tenant": tenant,
    }
