from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel


class DeleteAccountRequest(BaseModel):
    password: str
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_owner, require_admin

from .schemas import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantUserCreate,
    TenantUserResponse,
)
from app.modules.subscriptions.schemas import SubscriptionUpdate, SubscriptionResponse
from .service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("/users", response_model=list[TenantUserResponse])
def list_tenant_users(
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    return service.list_tenant_users(db, context["tenant"].id)


@router.post("/users", response_model=TenantUserResponse, status_code=201)
def create_tenant_user(
    data: TenantUserCreate,
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    return service.create_tenant_user(db, context["tenant"].id, data)


@router.delete("/users/{user_id}", status_code=204)
def remove_tenant_user(
    user_id: int,
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    service = TenantService()
    service.remove_tenant_user(
        db,
        context["tenant"].id,
        user_id,
        context["user"].id,
    )


@router.post("/me/new", response_model=TenantResponse)
def create_my_tenant(
    data: TenantCreate,
    response: Response,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    from app.modules.auth.token import create_access_token, create_refresh_token

    service = TenantService()
    user = context["user"]
    result = service.create_tenant(db, data, user.id)

    token_data = {
        "user_id": str(user.id),
        "tenant_id": str(result.id),
        "role": "owner",
    }

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=create_access_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=create_refresh_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    return result


@router.post("/", response_model=TenantResponse)
def create_tenant(
    user_id: int,
    data: TenantCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    from app.modules.auth.token import create_access_token, create_refresh_token

    service = TenantService()
    result = service.create_tenant(db, data, user_id)

    token_data = {
        "user_id": str(user_id),
        "tenant_id": str(result.id),
        "role": "owner",
    }

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=create_access_token(token_data),
        httponly=True,
        secure=False,  # True em prod
        samesite="lax",
        path="/",
    )

    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=create_refresh_token(token_data),
        httponly=True,
        secure=False,  # True em prod
        samesite="lax",
        path="/",
    )
    return result


@router.get("/", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)):
    service = TenantService()
    return service.list_tenants(db)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.get_tenant(db, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.update_tenant(db, tenant_id, data)


@router.delete("/me", status_code=204)
def delete_own_account(
    body: DeleteAccountRequest,
    db: Session = Depends(get_db),
    context: dict = Depends(require_owner),
):
    """Permanently deletes the tenant account and all its data."""
    from app.modules.auth.token import verify_password
    user = context["user"]
    if not verify_password(body.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha incorreta")
    service = TenantService()
    service.delete_own_tenant(db, context["tenant"], user)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    service = TenantService()
    service.delete_tenant(db, tenant_id)


@router.patch("/{tenant_id}/subscription", response_model=SubscriptionResponse)
def update_subscription(
    tenant_id: int,
    data: SubscriptionUpdate,
    db: Session = Depends(get_db),
):
    service = TenantService()
    return service.update_subscription(db, tenant_id, data)


@router.get("/admin/dashboard")
def get_admin_dashboard(
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin),
):
    from app.modules.tenants.models import Tenant
    from app.modules.clients.models import Client
    from app.modules.pets.models import Pet
    from app.modules.subscriptions.models import Subscription
    from app.modules.appointments.models import Appointment
    from app.modules.sales.models import Sale
    from sqlalchemy import text, func
    from datetime import datetime

    # 1. Bypass RLS for this transaction session
    db.execute(text("SET LOCAL row_security = OFF;"))

    # 2. Get all tenants
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()

    # 3. For each tenant, query statistics
    result = []
    for tenant in tenants:
        # Client count
        client_count = db.query(func.count(Client.id)).filter(Client.tenant_id == tenant.id).scalar()
        # Pet count
        pet_count = db.query(func.count(Pet.id)).filter(Pet.tenant_id == tenant.id).scalar()
        # Appointment count
        appointment_count = db.query(func.count(Appointment.id)).filter(Appointment.tenant_id == tenant.id).scalar()
        # Sale count
        sale_count = db.query(func.count(Sale.id)).filter(Sale.tenant_id == tenant.id).scalar()
        
        # Active subscription
        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).order_by(Subscription.id.desc()).first()

        # Tenure calculation
        tenure_days = (datetime.now() - tenant.created_at.replace(tzinfo=None)).days
        if tenure_days < 30:
            tenure = f"{tenure_days} dia(s)"
        else:
            tenure_months = tenure_days // 30
            tenure = f"{tenure_months} mês(es)"

        # Payment status
        payment_status = "no_subscription"
        plan_name = "Nenhum"
        current_period_end = None
        price_cents = 0
        
        if sub:
            plan_name = sub.plan.name if sub.plan else "Nenhum"
            current_period_end = sub.current_period_end.isoformat() if sub.current_period_end else None
            price_cents = sub.plan.price_cents if (sub.plan and sub.status in ("active", "trialing", "pending")) else 0
            
            if sub.status == "trialing":
                payment_status = "trial"
            elif sub.status == "active":
                payment_status = "paid"
            elif sub.status == "past_due":
                payment_status = "overdue"
            elif sub.status == "canceled":
                payment_status = "canceled"
            else:
                payment_status = sub.status

        result.append({
            "id": tenant.id,
            "name": tenant.name,
            "email": tenant.email,
            "phone": tenant.phone,
            "created_at": tenant.created_at.isoformat(),
            "tenure": tenure,
            "client_count": client_count,
            "pet_count": pet_count,
            "appointment_count": appointment_count,
            "sale_count": sale_count,
            "plan_name": plan_name,
            "price_cents": price_cents,
            "payment_status": payment_status,
            "current_period_end": current_period_end,
            "onboarding_step": tenant.onboarding_step,
        })

    return result

