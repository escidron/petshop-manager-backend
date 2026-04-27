from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.token import decode_token
from app.modules.tenants.models import Tenant
from app.modules.users.models import TenantUser, User
from app.modules.subscriptions.repository import SubscriptionRepository


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
            detail="Usuário ou empresa não encontrada",
        )
    
    subscription_repo = SubscriptionRepository()
    subscription = subscription_repo.get_active_by_tenant(db, tenant_id)
    tenant.subscription = subscription

    request.state.tenant_user = tenant_user

    return {
        "user": user,
        "tenant": tenant,
    }


def require_owner(
    request: Request,
    context: dict = Depends(get_current_tenant),
):
    tenant_user = request.state.tenant_user
    if tenant_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can perform this action",
        )
    return context


def require_active_subscription(
    context: dict = Depends(get_current_tenant),
):
    """
    Permite apenas operações de escrita quando a assinatura está ativa.
    - status == 'active' → OK
    - status == 'trialing' AND trial_ends_at > now → OK
    - qualquer outro caso → 403 com código 'subscription_required' ou 'trial_expired'
    """
    sub = context["tenant"].subscription

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="subscription_required",
        )

    now = datetime.now(timezone.utc)

    if sub.status == "active":
        # PIX não tem subscription recorrente: verifica se o período ainda é válido
        if sub.payment_method == "pix":
            period_end = sub.current_period_end
            if period_end is not None:
                if period_end.tzinfo is None:
                    period_end = period_end.replace(tzinfo=timezone.utc)
                if now > period_end:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="subscription_required",
                    )
        return context

    if sub.status == "trialing":
        trial_end = sub.trial_ends_at
        if trial_end is not None:
            # Garante comparação timezone-aware
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            if now < trial_end:
                return context
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="trial_expired",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="subscription_required",
    )
