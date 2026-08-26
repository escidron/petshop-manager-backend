from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.token import decode_token
from app.modules.tenants.models import Tenant
from app.modules.users.models import TenantUser, User
from app.modules.subscriptions.repository import SubscriptionRepository, SubscriptionChargeRepository

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
    if subscription and subscription.status in ("active", "pending") and subscription.current_period_end:
        period_end = subscription.current_period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end < datetime.now(timezone.utc):
            subscription = subscription_repo.update(db, subscription, {"status": "past_due"})

    if subscription:
        from app.modules.subscriptions.service import is_subscription_eligible_for_refund
        subscription.eligible_for_refund = is_subscription_eligible_for_refund(db, subscription)
                
    tenant.subscription = subscription

    request.state.tenant_user = tenant_user

    # Injeta a role e permissões específicas do usuário neste tenant
    user.role = tenant_user.role
    user.permissions = tenant_user.permissions or []

    # 🔐 Set RLS tenant ID for the session
    db.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tenant_id})

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


def require_admin(
    user: User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: apenas administradores do sistema podem realizar esta ação",
        )
    return user



def require_active_subscription(
    context: dict = Depends(get_current_tenant),
):
    """
    Permite apenas operações de escrita quando a assinatura está ativa.
    - status == 'active' → OK (para PIX, tolerância de até 3 dias após o vencimento)
    - status == 'past_due' AND vencimento + 3 dias > agora → OK (período de tolerância/grace period)
    - status == 'trialing' AND trial_ends_at > agora → OK
    - qualquer outro caso → 403 com código 'subscription_required' ou 'trial_expired'
    """
    from datetime import timedelta
    
    tenant = context["tenant"]
    if tenant.feature_flags and tenant.feature_flags.get("free_access"):
        return context

    sub = tenant.subscription
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura necessária. Acesse Configurações > Planos e Cobrança para assinar um plano.",
        )

    now = datetime.now(timezone.utc)

    if sub.status == "active":
        period_end = sub.current_period_end
        if period_end is not None:
            if period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            # PIX: tolerância de 3 dias de grace period; outros (cartão) vencem na data
            grace_days = 3 if sub.payment_method == "pix" else 0
            if now > period_end + timedelta(days=grace_days):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Assinatura expirada. Acesse Configurações > Planos e Cobrança para renovar.",
                )
        return context

    if sub.status == "past_due":
        period_end = sub.current_period_end
        if period_end is not None:
            if period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            # Permite operações dentro do grace period de 3 dias
            if now <= period_end + timedelta(days=3):
                return context
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura pendente ou atrasada. Acesse Configurações > Planos e Cobrança para regularizar seu pagamento.",
        )

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
            detail="Seu período de teste grátis expirou. Acesse Configurações > Planos e Cobrança para assinar o Plano Profissional e continuar usando o sistema.",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Assinatura necessária. Acesse Configurações > Planos e Cobrança para ativar sua conta.",
    )

