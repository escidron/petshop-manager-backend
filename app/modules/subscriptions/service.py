import hashlib
import hmac
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.modules.plans.models import Plan
from app.modules.subscriptions.models import Subscription
from app.modules.subscriptions.repository import SubscriptionRepository
from app.modules.tenants.models import Tenant

_repo = SubscriptionRepository()

PAGARME_BASE_URL = "https://api.pagar.me/core/v5"


def _pagarme_client() -> httpx.Client:
    return httpx.Client(
        base_url=PAGARME_BASE_URL,
        auth=(settings.PAGARME_SECRET_KEY, ""),
        timeout=30,
    )


def _ensure_pagarme_customer(db: Session, tenant: Tenant, user_email: str, document: str | None = None) -> str:
    phone_digits = "".join(filter(str.isdigit, tenant.phone or ""))
    area_code = phone_digits[:2] if len(phone_digits) >= 2 else "11"
    phone_number = phone_digits[2:] if len(phone_digits) > 2 else "999999999"

    doc_digits = "".join(filter(str.isdigit, document or ""))
    doc_type = "cpf" if len(doc_digits) <= 11 else "cnpj"

    if tenant.pagarme_customer_id:
        # Customer already exists — update document if provided
        if doc_digits:
            with _pagarme_client() as client:
                client.put(f"/customers/{tenant.pagarme_customer_id}", json={
                    "name": tenant.name,
                    "email": user_email,
                    "type": "individual",
                    "country": "BR",
                    "document": doc_digits,
                    "document_type": doc_type,
                    "phones": {
                        "mobile_phone": {
                            "country_code": "55",
                            "area_code": area_code,
                            "number": phone_number,
                        }
                    },
                })
        return tenant.pagarme_customer_id

    payload: dict = {
        "name": tenant.name,
        "email": user_email,
        "type": "individual",
        "country": "BR",
        "phones": {
            "mobile_phone": {
                "country_code": "55",
                "area_code": area_code,
                "number": phone_number,
            }
        },
    }
    if doc_digits:
        payload["document"] = doc_digits
        payload["document_type"] = doc_type

    with _pagarme_client() as client:
        resp = client.post("/customers", json=payload)
        print("=== PAGARME CUSTOMER ===")
        print("STATUS:", resp.status_code)
        print("RESPONSE:", resp.text)
        print("========================")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao criar cliente no Pagar.me: {resp.text}")

    customer = resp.json()
    tenant.pagarme_customer_id = customer["id"]
    db.add(tenant)
    db.flush()

    return customer["id"]


def create_checkout(
    db: Session,
    tenant: Tenant,
    user_email: str,
    plan_code: str,
    card_token: str | None = None,
    payment_method: str = "credit_card",
    document: str | None = None,
    billing_address: dict | None = None,
) -> dict:
    plan: Plan | None = db.query(Plan).filter(Plan.code == plan_code, Plan.is_active == True).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    # Free trial: sem cobrança
    if plan_code == "FREE_TRIAL":
        trial_ends_at = datetime.now(timezone.utc) + timedelta(days=plan.trial_days or 14)
        _repo.create(
            db=db,
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="trialing",
            current_period_end=trial_ends_at,
            trial_ends_at=trial_ends_at,
        )
        db.commit()
        return {"status": "trialing", "trial_ends_at": trial_ends_at.isoformat()}

    if not plan.pagarme_plan_id:
        raise HTTPException(
            status_code=422,
            detail="Este plano ainda não possui um ID configurado no Pagar.me",
        )

    customer_id = _ensure_pagarme_customer(db, tenant, user_email, document)

    # PIX: cobrança avulsa (Pagar.me não suporta PIX em subscriptions)
    if payment_method == "pix":
        return _checkout_pix(db, tenant, customer_id, plan)

    # Cartão: cria subscription no Pagar.me
    if not card_token:
        raise HTTPException(status_code=422, detail="card_token obrigatório para pagamento com cartão")

    # Salva o cartão no customer → obtém card_id permanente
    with _pagarme_client() as client:
        addr = billing_address or {
            "country": "BR",
            "state": "SP",
            "city": "São Paulo",
            "zip_code": "01310100",
            "line_1": "Não informado",
        }
        card_resp = client.post(
            f"/customers/{customer_id}/cards",
            json={"token": card_token, "billing_address": addr},
        )
        if card_resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao salvar cartão: {card_resp.text}")

    sub_payload: dict = {
        "customer_id": customer_id,
        "plan_id": plan.pagarme_plan_id,
        "payment_method": "credit_card",
        "card_id": card_resp.json()["id"],
    }

    with _pagarme_client() as client:
        resp = client.post("/subscriptions", json=sub_payload)
        print("=== PAGARME SUBSCRIPTION ===")
        print("STATUS:", resp.status_code)
        print("PAYLOAD:", sub_payload)
        print("RESPONSE:", resp.text)
        print("============================")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao criar assinatura no Pagar.me: {resp.text}")

    pagarme_sub = resp.json()

    period_end = datetime.now(timezone.utc) + timedelta(days=30)

    existing = _repo.get_active_by_tenant(db, tenant.id)
    if existing:
        _repo.update(db, existing, {
            "plan_id": plan.id,
            "status": _map_status(pagarme_sub.get("status", "pending")),
            "pagarme_subscription_id": pagarme_sub["id"],
            "current_period_end": period_end,
            "trial_ends_at": None,
            "canceled_at": None,
            "payment_method": "card",
        })
    else:
        sub = _repo.create(
            db=db,
            tenant_id=tenant.id,
            plan_id=plan.id,
            status=_map_status(pagarme_sub.get("status", "pending")),
            current_period_end=period_end,
            pagarme_subscription_id=pagarme_sub["id"],
        )
        _repo.update(db, sub, {"payment_method": "card"})

    db.commit()

    return {
        "pagarme_subscription_id": pagarme_sub["id"],
        "status": pagarme_sub.get("status"),
    }


def _checkout_pix(db: Session, tenant: Tenant, customer_id: str, plan: Plan) -> dict:
    """Cria cobrança avulsa PIX (Pagar.me não suporta PIX em subscriptions)."""
    charge_payload = {
        "customer_id": customer_id,
        "payment": {
            "payment_method": "pix",
            "pix": {"expires_in": 3600},
        },
        "amount": plan.price_cents,
        "currency": plan.currency or "BRL",
    }

    with _pagarme_client() as client:
        resp = client.post("/charges", json=charge_payload)
        print("=== PAGARME PIX CHARGE ===")
        print("STATUS:", resp.status_code)
        print("PAYLOAD:", charge_payload)
        print("RESPONSE:", resp.text)
        print("==========================")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao gerar cobrança PIX: {resp.text}")

    charge = resp.json()
    charge_id = charge["id"]
    pix_data = charge.get("last_transaction", {})

    period_end = datetime.now(timezone.utc) + timedelta(days=30)

    existing = _repo.get_active_by_tenant(db, tenant.id)
    if existing:
        _repo.update(db, existing, {
            "plan_id": plan.id,
            "status": "pending",
            "pagarme_subscription_id": charge_id,
            "current_period_end": period_end,
            "trial_ends_at": None,
            "canceled_at": None,
            "payment_method": "pix",
        })
    else:
        sub = _repo.create(
            db=db,
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="pending",
            current_period_end=period_end,
            pagarme_subscription_id=charge_id,
        )
        _repo.update(db, sub, {"payment_method": "pix"})

    db.commit()

    return {
        "pagarme_subscription_id": charge_id,
        "status": "pending",
        "pix_qr_code": pix_data.get("qr_code"),
        "pix_qr_code_url": pix_data.get("qr_code_url"),
        "expires_at": pix_data.get("expires_at"),
    }


def add_payment_method(
    db: Session,
    tenant: Tenant,
    user_email: str,
    card_token: str,
    billing_address: dict | None = None,
    document: str | None = None,
) -> dict:
    customer_id = _ensure_pagarme_customer(db, tenant, user_email, document)

    addr = billing_address or {
        "country": "BR",
        "state": "SP",
        "city": "São Paulo",
        "zip_code": "01310100",
        "line_1": "Não informado",
    }

    with _pagarme_client() as client:
        resp = client.post(
            f"/customers/{customer_id}/cards",
            json={"token": card_token, "billing_address": addr},
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao salvar cartão: {resp.text}")

    card = resp.json()
    return {
        "id": card["id"],
        "brand": card.get("brand", ""),
        "last4": card.get("last_four_digits", ""),
        "exp_month": int(card.get("exp_month", 0)),
        "exp_year": int(card.get("exp_year", 0)),
        "is_default": False,
    }


def cancel_subscription(db: Session, tenant: Tenant) -> Subscription:
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    if sub.pagarme_subscription_id:
        with _pagarme_client() as client:
            resp = client.delete(f"/subscriptions/{sub.pagarme_subscription_id}")
            if resp.status_code not in (200, 204):
                raise HTTPException(status_code=502, detail=f"Erro ao cancelar no Pagar.me: {resp.text}")

    return _repo.update(db, sub, {
        "status": "canceled",
        "canceled_at": datetime.now(timezone.utc),
    })


def list_payment_methods(db: Session, tenant: Tenant) -> list[dict]:
    if not tenant.pagarme_customer_id:
        return []

    # Descobre qual cartão está ativo na assinatura
    active_card_id: str | None = None
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if sub and sub.pagarme_subscription_id:
        with _pagarme_client() as client:
            sub_resp = client.get(f"/subscriptions/{sub.pagarme_subscription_id}")
            if sub_resp.status_code == 200:
                active_card_id = sub_resp.json().get("card", {}).get("id")

    with _pagarme_client() as client:
        resp = client.get(f"/customers/{tenant.pagarme_customer_id}/cards")
        if resp.status_code != 200:
            return []

    cards = resp.json().get("data", [])
    return [
        {
            "id": c["id"],
            "brand": c.get("brand", ""),
            "last4": c.get("last_four_digits", ""),
            "exp_month": int(c.get("exp_month", 0)),
            "exp_year": int(c.get("exp_year", 0)),
            "is_default": c["id"] == active_card_id,
        }
        for c in cards
    ]


def set_default_payment_method(db: Session, tenant: Tenant, pm_id: str) -> None:
    if not tenant.pagarme_customer_id:
        raise HTTPException(status_code=400, detail="Cliente Pagar.me não encontrado")

    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub or not sub.pagarme_subscription_id:
        raise HTTPException(status_code=400, detail="Nenhuma assinatura ativa encontrada")

    with _pagarme_client() as client:
        resp = client.patch(
            f"/subscriptions/{sub.pagarme_subscription_id}/card",
            json={"card_id": pm_id},
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao atualizar cartão da assinatura: {resp.text}")


def detach_payment_method(tenant: Tenant, pm_id: str) -> None:
    if not tenant.pagarme_customer_id:
        raise HTTPException(status_code=400, detail="Cliente Pagar.me não encontrado")
    with _pagarme_client() as client:
        resp = client.delete(f"/customers/{tenant.pagarme_customer_id}/cards/{pm_id}")
        if resp.status_code not in (200, 204):
            raise HTTPException(status_code=502, detail="Erro ao remover cartão")


def create_card_token(card_data: dict) -> str:
    """Tokeniza um cartão via Pagar.me (usado pelo front para não trafegar dados sensíveis)."""
    with _pagarme_client() as client:
        resp = client.post("/tokens?appId=" + settings.PAGARME_PUBLIC_KEY, json={
            "type": "card",
            "card": card_data,
        })
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao tokenizar cartão: {resp.text}")
    return resp.json()["id"]


def handle_webhook_event(payload: bytes, sig_header: str) -> None:
    if settings.PAGARME_WEBHOOK_SECRET:
        expected = hmac.new(
            settings.PAGARME_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            raise HTTPException(status_code=400, detail="Assinatura do webhook inválida")

    import json
    from app.config.database import SessionLocal

    event = json.loads(payload)
    db = SessionLocal()
    try:
        event_type = event.get("type", "")

        if event_type == "subscription.payment_succeeded":
            _on_payment_succeeded(db, event["data"])

        elif event_type == "subscription.payment_failed":
            _on_payment_failed(db, event["data"])

        elif event_type in ("subscription.canceled", "subscription.deactivated"):
            _on_subscription_canceled(db, event["data"])

        elif event_type == "subscription.created":
            _on_subscription_created(db, event["data"])

        elif event_type == "charge.paid":
            _on_pix_charge_paid(db, event["data"])

    finally:
        db.close()


def _map_status(pagarme_status: str) -> str:
    mapping = {
        "active": "active",
        "trialing": "trialing",
        "pending": "pending",
        "canceled": "canceled",
        "future": "incomplete",
        "unpaid": "past_due",
        "failed": "failed",
        "deactivated": "canceled",
    }
    return mapping.get(pagarme_status, "incomplete")


def _on_payment_succeeded(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        _repo.update(db, sub, {
            "status": "active",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        })


def _on_payment_failed(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        _repo.update(db, sub, {"status": "past_due"})


def _on_subscription_canceled(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        _repo.update(db, sub, {
            "status": "canceled",
            "canceled_at": datetime.now(timezone.utc),
        })


def _on_subscription_created(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        _repo.update(db, sub, {"status": _map_status(data.get("status", "pending"))})


def _on_pix_charge_paid(db: Session, data: dict) -> None:
    """Ativa a subscription PIX quando o pagamento avulso for confirmado."""
    charge_id = data.get("id")
    if not charge_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, charge_id)
    if sub and sub.payment_method == "pix":
        _repo.update(db, sub, {
            "status": "active",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        })
        db.commit()
