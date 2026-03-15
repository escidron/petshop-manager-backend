from sqlalchemy.orm import Session

from app.modules.plans.models import Plan
from app.modules.tenants.models import TenantType


def seed_plans(db: Session):
    plans = [
        {
            "name": "Teste Gratis",
            "code": "FREE_TRIAL",
            "price_cents": 0,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 14,
            "is_active": True,
        },
        {
            "name": "Plano Mensal",
            "code": "MONTHLY",
            "price_cents": 9990,  # 99.90 em centavos
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
    ]

    for plan_data in plans:
        existing = db.query(Plan).filter(
            Plan.code == plan_data["code"]
        ).first()

        if not existing:
            plan = Plan(**plan_data)
            db.add(plan)

    db.commit()


def seed_tenant_types(db: Session):
    types = [
        {
            "code": "petshop",
            "name": "Petshop / Banho e Tosa",
            "is_active": True,
        }
    ]

    for type_data in types:
        existing = db.query(TenantType).filter(
            TenantType.code == type_data["code"]
        ).first()

        if not existing:
            t_type = TenantType(**type_data)
            db.add(t_type)

    db.commit()
