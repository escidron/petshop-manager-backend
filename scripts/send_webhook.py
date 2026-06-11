"""
Como rodar os testes localmente:

# 1. Primeira Compra (Sucesso):
# poetry run python scripts/send_webhook.py --tenant 15 --scenario created

# 2. Renovação do Ciclo / Segundo Mês Pago (Sucesso):
# poetry run python scripts/send_webhook.py --tenant 15 --scenario paid

# 3. Falha no Pagamento / Cartão Recusado ou Removido (Inadimplente/Atrasado):
# poetry run python scripts/send_webhook.py --tenant 15 --scenario failed

# 4. Inadimplente Definitiva (Unpaid):
# poetry run python scripts/send_webhook.py --tenant 15 --scenario unpaid

# 5. Cancelamento de Assinatura:
# poetry run python scripts/send_webhook.py --tenant 15 --scenario canceled
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config.settings import settings

SCENARIOS = {
    "created": {
        "event": "subscription.created",
        "description": "Primeira cobrança / Assinatura criada com sucesso.",
        "status": "active"
    },
    "paid": {
        "event": "subscription.payment_succeeded",
        "description": "Pagamento mensal aprovado (renovação de ciclo).",
        "status": "active"
    },
    "failed": {
        "event": "subscription.payment_failed",
        "description": "Falha na cobrança (cartão recusado / removido / expirado).",
        "status": "past_due"
    },
    "unpaid": {
        "event": "subscription.unpaid",
        "description": "Assinatura inadimplente definitiva após todas as retentativas falharem.",
        "status": "past_due"
    },
    "canceled": {
        "event": "subscription.canceled",
        "description": "Assinatura cancelada.",
        "status": "canceled"
    }
}


def get_sub_id_from_db(tenant_id: int) -> str:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT pagarme_subscription_id
                FROM subscriptions
                WHERE tenant_id = :tenant_id
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id},
        ).fetchone()

    if not row or not row[0]:
        print(f"[ERRO] Nenhuma assinatura ativa com ID Pagar.me encontrada para tenant_id={tenant_id}")
        sys.exit(1)

    return row[0]


def send_webhook(pagarme_sub_id: str, scenario_key: str, server_url: str):
    scenario = SCENARIOS[scenario_key]
    event_type = scenario["event"]
    
    print(f"\n[+] Simulando cenário: '{scenario_key}' ({scenario['description']})")
    print(f"    Evento: {event_type} | ID Assinatura: {pagarme_sub_id}")

    payload_dict = {
        "type": event_type,
        "data": {
            "id": pagarme_sub_id,
            "status": scenario["status"],
            "current_cycle": {
                "status": "billed" if scenario_key in ("created", "paid") else "failed"
            }
        }
    }

    payload = json.dumps(payload_dict).encode()
    headers = {"Content-Type": "application/json"}

    if settings.PAGARME_WEBHOOK_SECRET:
        sig = hmac.new(settings.PAGARME_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        headers["x-hub-signature"] = sig
        print("    Assinatura HMAC adicionada nos cabeçalhos.")

    url = f"{server_url}/api/v1/webhooks/pagarme"
    try:
        resp = httpx.post(url, content=payload, headers=headers, timeout=10)
        print(f"    POST {url} -> Status HTTP {resp.status_code}")
        print(f"    Retorno do servidor: {resp.text}")
        if resp.status_code == 200:
            print("[OK] Cenário processado com sucesso!")
        else:
            print("[X] O servidor retornou um erro ao processar o webhook.")
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao servidor: {e}")


def main():
    parser = argparse.ArgumentParser(description="Simula cenários de assinatura enviando webhooks locais.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", type=int, help="tenant_id para buscar a assinatura automaticamente no banco local")
    group.add_argument("--sub", type=str, help="ID direto da assinatura no Pagar.me (sub_...)")
    
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        required=True,
        help="Cenário de faturamento a ser simulado"
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="URL base do seu servidor local (padrão: http://localhost:8000)"
    )

    args = parser.parse_args()

    pagarme_sub_id = get_sub_id_from_db(args.tenant) if args.tenant else args.sub
    send_webhook(pagarme_sub_id, args.scenario, args.server.rstrip("/"))


if __name__ == "__main__":
    main()
