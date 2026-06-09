"""
Cria o plano MONTHLY no Pagar.me e atualiza o pagarme_plan_id no banco local.
Execute com: .venv\Scripts\python.exe scratch\create_pagarme_plan.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\Projetos Front-end\petshop-manager\back-end")

import httpx
from app.config.settings import settings
from app.config.database import SessionLocal
from app.modules.plans.models import Plan

PAGARME_BASE_URL = "https://api.pagar.me/core/v5"

def pagarme_client():
    return httpx.Client(
        base_url=PAGARME_BASE_URL,
        auth=(settings.PAGARME_SECRET_KEY, ""),
        timeout=30,
    )

db = SessionLocal()
try:
    # Verifica se o plano ja existe no banco
    plan = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    if not plan:
        print("[ERRO] Plano MONTHLY nao encontrado no banco. Rode os seeds primeiro: make seed")
        sys.exit(1)

    print(f"Plano no banco: {plan.name} | preco: R$ {plan.price_cents / 100:.2f} | pagarme_plan_id atual: {plan.pagarme_plan_id}")
    print()

    # Cria o plano no Pagar.me
    payload = {
        "name": "Plano Mensal - PetShop Manager",
        "description": "Assinatura mensal do sistema PetShop Manager",
        "currency": "BRL",
        "interval": "month",
        "interval_count": 1,
        "billing_type": "prepaid",
        "payment_methods": ["credit_card"],
        "items": [
            {
                "name": "Plano Mensal",
                "quantity": 1,
                "pricing_scheme": {
                    "price": 9990,  # 99.90 em centavos
                    "scheme_type": "unit",
                },
            }
        ],
    }

    print("Criando plano no Pagarme...")
    with pagarme_client() as client:
        resp = client.post("/plans", json=payload)
        print(f"Status: {resp.status_code}")
        if resp.status_code not in (200, 201):
            print(f"[ERRO] {resp.text}")
            sys.exit(1)

    pagarme_plan = resp.json()
    plan_id = pagarme_plan["id"]
    print(f"[OK] Plano criado no Pagarme: {plan_id}")
    print(f"     Nome: {pagarme_plan.get('name')}")
    print(f"     Preco: R$ {pagarme_plan['items'][0]['pricing_scheme']['price'] / 100:.2f}")

    # Atualiza no banco local
    plan.pagarme_plan_id = plan_id
    db.commit()
    print(f"\n[OK] pagarme_plan_id atualizado no banco para: {plan_id}")

except Exception as e:
    db.rollback()
    print(f"[ERRO] {e}")
    raise
finally:
    db.close()
