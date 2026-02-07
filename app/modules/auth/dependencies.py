from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.token import decode_token
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
) -> TenantUser:
    token = request.cookies.get("access_token")
    payload = decode_token(token)

    tenant_user = (
        db.query(TenantUser)
        .filter(
            TenantUser.user_id == payload["user_id"],
            TenantUser.tenant_id == payload["tenant_id"],
        )
        .first()
    )

    if not tenant_user:
        raise HTTPException(status_code=403)

    request.state.tenant_user = tenant_user
    return tenant_user