"""
Script para criar os prices no Stripe e atualizar o banco de dados.
Uso: poetry run python scripts/seed_stripe_prices.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stripe
from app.config.settings import settings
from app.config.database import SessionLocal
from app.modules.plans.models import Plan

stripe.api_key = settings.STRIPE_SECRET_KEY

PLANS = [
    {
        "code": "MONTHLY",
        "stripe_product_name": "Petshop Manager - Plano Mensal",
        "unit_amount": 9990,  # R$ 99,90 em centavos
        "currency": "brl",
        "interval": "month",
    },
]


def seed():
    db = SessionLocal()
    try:
        for plan_data in PLANS:
            plan = db.query(Plan).filter(Plan.code == plan_data["code"]).first()
            if not plan:
                print(f"[SKIP] Plano '{plan_data['code']}' não encontrado no banco.")
                continue

            if plan.stripe_price_id:
                print(f"[SKIP] Plano '{plan_data['code']}' já tem stripe_price_id: {plan.stripe_price_id}")
                continue

            price = stripe.Price.create(
                unit_amount=plan_data["unit_amount"],
                currency=plan_data["currency"],
                recurring={"interval": plan_data["interval"]},
                product_data={"name": plan_data["stripe_product_name"]},
            )

            plan.stripe_price_id = price.id
            db.add(plan)
            db.commit()

            print(f"[OK] Plano '{plan_data['code']}' → stripe_price_id: {price.id}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
