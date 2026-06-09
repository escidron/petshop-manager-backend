import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config.settings import settings
from app.config.database import SessionLocal
from app.modules.plans.models import Plan

PAGARME_BASE_URL = "https://api.pagar.me/core/v5"

def main():
    db = SessionLocal()
    try:
        # 1. Verifica/cria o plano no banco local
        plan = db.query(Plan).filter(Plan.code == "DAILY").first()
        if not plan:
            plan = Plan(
                code="DAILY",
                name="Plano Diário Teste (R$ 10,00)",
                price_cents=1000,
                currency="BRL",
                billing_cycle="day",
                trial_days=0,
                is_active=True
            )
            db.add(plan)
            db.flush()
            print("[OK] Plano DAILY criado no banco de dados local.")

        if plan.pagarme_plan_id:
            print(f"[SKIP] Plano DAILY já registrado no Pagar.me com ID: {plan.pagarme_plan_id}")
            return

        # 2. Envia para o Pagar.me
        print(f"Registrando plano DAILY no Pagar.me...")
        with httpx.Client(
            base_url=PAGARME_BASE_URL,
            auth=(settings.PAGARME_SECRET_KEY, ""),
            timeout=30,
        ) as client:
            resp = client.post("/plans", json={
                "name": plan.name,
                "interval": "day",
                "interval_count": 1,
                "billing_type": "prepaid",
                "payment_methods": ["credit_card"],
                "items": [
                    {
                        "name": plan.name,
                        "quantity": 1,
                        "pricing_scheme": {
                            "price": plan.price_cents,
                        },
                    }
                ],
                "currency": plan.currency,
            })

            if resp.status_code not in (200, 201):
                print(f"[ERRO] Falha ao registrar plano no Pagar.me: {resp.text}")
                return

            pagarme_plan = resp.json()
            plan.pagarme_plan_id = pagarme_plan["id"]
            db.commit()
            print(f"[OK] Plano DAILY registrado no Pagar.me com ID: {pagarme_plan['id']}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
