"""
Cria os planos no Pagar.me e salva o pagarme_plan_id em cada Plan do banco.
Uso: python scripts/seed_pagarme_plans.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config.settings import settings
from app.config.database import SessionLocal
from app.modules.plans.models import Plan

PAGARME_BASE_URL = "https://api.pagar.me/core/v5"

PLANS_TO_SEED = [
    {
        "code": "MONTHLY",
        "name": "PetControle - Plano Mensal",
        "interval": "month",
        "interval_count": 1,
    },
]


def main():
    db = SessionLocal()
    try:
        with httpx.Client(
            base_url=PAGARME_BASE_URL,
            auth=(settings.PAGARME_SECRET_KEY, ""),
            timeout=30,
        ) as client:
            for plan_data in PLANS_TO_SEED:
                plan = db.query(Plan).filter(Plan.code == plan_data["code"]).first()
                if not plan:
                    print(f"[SKIP] Plano '{plan_data['code']}' não encontrado no banco")
                    continue

                if plan.pagarme_plan_id:
                    print(f"[SKIP] Plano '{plan_data['code']}' já tem pagarme_plan_id: {plan.pagarme_plan_id}")
                    continue

                resp = client.post("/plans", json={
                    "name": plan_data["name"],
                    "interval": plan_data["interval"],
                    "interval_count": plan_data["interval_count"],
                    "billing_type": "prepaid",
                    "payment_methods": ["credit_card", "boleto"],
                    "items": [
                        {
                            "name": plan_data["name"],
                            "quantity": 1,
                            "pricing_scheme": {
                                "price": plan.price_cents,
                            },
                        }
                    ],
                    "currency": "BRL",
                })

                if resp.status_code not in (200, 201):
                    print(f"[ERRO] Plano '{plan_data['code']}': {resp.text}")
                    continue

                pagarme_plan = resp.json()
                plan.pagarme_plan_id = pagarme_plan["id"]
                db.commit()
                print(f"[OK] Plano '{plan_data['code']}' → pagarme_plan_id: {pagarme_plan['id']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
