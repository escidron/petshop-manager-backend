"""
Simula cobrança recorrente de assinatura no Pagar.me (sandbox).

O que o script faz:
  1. Cria um novo ciclo no Pagar.me via POST /cycles (fica visível no dashboard)
  2. Dispara o webhook subscription.payment_succeeded direto no seu servidor
     para atualizar o banco — igual ao que o Pagar.me faria na data de cobrança.

Por que o passo 2 é necessário:
  POST /cycles cria um ciclo FUTURO (unbilled). O Pagar.me só dispara
  subscription.payment_succeeded na data de billing real. No sandbox não há
  como adiantar o tempo, então simulamos o webhook manualmente.

Uso:
  # Pelo tenant_id (busca a subscription ativa no banco)
  python scripts/test_recurring_charge.py --tenant 1

  # Pelo pagarme_subscription_id direto
  python scripts/test_recurring_charge.py --sub sub_XXXXXXXX

  # Aponta para servidor diferente (padrão: http://localhost:8000)
  python scripts/test_recurring_charge.py --tenant 1 --server https://abc.ngrok.io
"""
import sys
import os
import argparse
import hashlib
import hmac
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import create_engine, text
from app.config.settings import settings

PAGARME_BASE_URL = "https://api.pagar.me/core/v5"


def get_sub_id_from_db(tenant_id: int) -> str:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, status, pagarme_subscription_id, current_period_end, payment_method
                FROM subscriptions
                WHERE tenant_id = :tenant_id
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id},
        ).fetchone()

    if not row:
        print(f"[ERRO] Nenhuma subscription encontrada para tenant_id={tenant_id}")
        sys.exit(1)

    sub_id, status, pagarme_id, period_end, payment_method = row

    if not pagarme_id:
        print(f"[ERRO] Subscription id={sub_id} não tem pagarme_subscription_id")
        print("       PIX avulso não suporta ciclo forçado — apenas assinaturas de cartão.")
        sys.exit(1)

    if payment_method == "pix":
        print(f"[ERRO] Subscription id={sub_id} é PIX avulso — não suporta ciclo recorrente no Pagar.me.")
        sys.exit(1)

    print(f"[INFO] Subscription: id={sub_id} | status={status} | pagarme_id={pagarme_id}")
    print(f"[INFO] current_period_end atual: {period_end}")
    return pagarme_id


def create_cycle_in_pagarme(pagarme_sub_id: str) -> bool:
    """Cria o próximo ciclo no Pagar.me (fica visível no dashboard). Retorna True se ok."""
    print(f"\n[1/2] Criando ciclo no Pagar.me para: {pagarme_sub_id}")

    with httpx.Client(base_url=PAGARME_BASE_URL, auth=(settings.PAGARME_SECRET_KEY, ""), timeout=30) as client:
        resp = client.get(f"/subscriptions/{pagarme_sub_id}")
        if resp.status_code != 200:
            print(f"[ERRO] Não foi possível buscar a subscription: {resp.text}")
            return False

        sub_data = resp.json()
        print(f"       Status: {sub_data.get('status')} | Próximo ciclo: {sub_data.get('next_billing_at')}")

        cycle_resp = client.post(f"/subscriptions/{pagarme_sub_id}/cycles")
        print(f"       POST /cycles → HTTP {cycle_resp.status_code}")

        if cycle_resp.status_code not in (200, 201):
            print(f"[AVISO] Falha ao criar ciclo: {cycle_resp.text}")
            print("        Continuando para simular o webhook mesmo assim...")
            return False

        cycle = cycle_resp.json()
        print(f"[OK]   Ciclo criado no Pagar.me!")
        print(f"       cycle_id   : {cycle.get('id')}")
        print(f"       status     : {cycle.get('status')}")
        print(f"       billing_at : {cycle.get('billing_at')}")
        return True


def simulate_payment_webhook(pagarme_sub_id: str, server_url: str) -> None:
    """Dispara subscription.payment_succeeded direto no seu servidor para atualizar o banco."""
    print(f"\n[2/2] Simulando webhook subscription.payment_succeeded → {server_url}")

    payload = json.dumps({
        "type": "subscription.payment_succeeded",
        "data": {"id": pagarme_sub_id},
    }).encode()

    headers = {"Content-Type": "application/json"}

    # Assina com HMAC se o secret estiver configurado
    if settings.PAGARME_WEBHOOK_SECRET:
        sig = hmac.new(settings.PAGARME_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        headers["x-hub-signature"] = sig
        print("       Assinatura HMAC incluída.")

    resp = httpx.post(f"{server_url}/api/v1/webhooks/pagarme", content=payload, headers=headers, timeout=10)
    print(f"       HTTP {resp.status_code} → {resp.text}")

    if resp.status_code == 200:
        print("[OK]   Webhook processado com sucesso!")
        print(f"\n       Verifique o banco:")
        print(f"       SELECT status, current_period_end FROM subscriptions")
        print(f"       WHERE pagarme_subscription_id = '{pagarme_sub_id}';")
    else:
        print(f"[ERRO] Webhook retornou erro. Verifique se o servidor está rodando em {server_url}")


def main():
    parser = argparse.ArgumentParser(description="Simula cobrança recorrente no Pagar.me sandbox")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", type=int, help="tenant_id para buscar a subscription no banco")
    group.add_argument("--sub", type=str, help="pagarme_subscription_id direto")
    parser.add_argument("--server", default="http://localhost:8000", help="URL base do seu servidor (padrão: http://localhost:8000)")
    args = parser.parse_args()

    pagarme_sub_id = get_sub_id_from_db(args.tenant) if args.tenant else args.sub

    create_cycle_in_pagarme(pagarme_sub_id)
    simulate_payment_webhook(pagarme_sub_id, args.server.rstrip("/"))


if __name__ == "__main__":
    main()
