import hashlib
import hmac
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.modules.plans.models import Plan
from app.modules.tenants.models import Tenant
from app.modules.subscriptions.models import Subscription, SubscriptionCharge, TenantCard
from app.modules.subscriptions.repository import SubscriptionRepository, SubscriptionChargeRepository

_repo = SubscriptionRepository()
_charge_repo = SubscriptionChargeRepository()


PAGARME_BASE_URL = "https://api.pagar.me/core/v5"


def _pagarme_client() -> httpx.Client:
    return httpx.Client(
        base_url=PAGARME_BASE_URL,
        auth=(settings.PAGARME_SECRET_KEY, ""),
        timeout=30,
    )


def _ensure_pagarme_customer(
    db: Session,
    tenant: Tenant,
    user_email: str,
    user_name: str,
    document: str | None = None,
) -> str:
    """Garante que existe um customer no Pagar.me para este tenant.

    O "Nome" no PagarMe é o nome real do owner (pessoa física). A identificação
    de qual tenant pertence cada cobrança/subscription é feita via metadata
    (tenant_id, tenant_name) que já é enviada em cada subscription.
    """
    phone_digits = "".join(filter(str.isdigit, tenant.phone or ""))
    area_code = phone_digits[:2] if len(phone_digits) >= 2 else "11"
    phone_number = phone_digits[2:] if len(phone_digits) > 2 else "999999999"

    doc_digits = "".join(filter(str.isdigit, document or ""))
    doc_type = "cpf" if len(doc_digits) <= 11 else "cnpj"
    if tenant.pagarme_customer_id:
        # Verifica se o customer realmente existe e está acessível com as credenciais atuais
        with _pagarme_client() as client:
            resp = client.get(f"/customers/{tenant.pagarme_customer_id}")
            if resp.status_code == 200:
                # Customer existe e está acessível — só atualiza o documento se fornecido
                if doc_digits:
                    client.put(f"/customers/{tenant.pagarme_customer_id}", json={
                        "document": doc_digits,
                        "document_type": doc_type,
                    })
                return tenant.pagarme_customer_id
            else:
                # Se der 401 (Não autorizado) ou 404 (Não encontrado), o ID pertence a outra conta
                # ou não existe mais. Vamos limpar o ID e gerar um novo.
                print(f"[WARN] Customer {tenant.pagarme_customer_id} inválido/inacessível na conta atual. Gerando novo.")
                tenant.pagarme_customer_id = None
                db.add(tenant)
                db.flush()

    # Não incluímos o document (CPF) na criação para evitar que o PagarMe
    # deduplique por CPF e retorne o mesmo customer para todos os tenants do
    # mesmo owner. O code tenant_{id} garante unicidade por tenant.
    # O documento é atualizado separadamente via PUT após a criação.
    payload: dict = {
        "code": f"tenant_{tenant.id}",
        "name": user_name,
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

    with _pagarme_client() as client:
        resp = client.post("/customers", json=payload)
        print("=== PAGARME CUSTOMER ===")
        print("STATUS:", resp.status_code)
        print("RESPONSE:", resp.text)
        print("========================")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao criar cliente no Pagar.me: {resp.text}")

    customer = resp.json()
    customer_id = customer["id"]
    tenant.pagarme_customer_id = customer_id
    db.add(tenant)
    db.flush()

    # Agora que o customer foi criado (único por tenant), associa o documento via PUT
    if doc_digits:
        with _pagarme_client() as client:
            client.put(f"/customers/{customer_id}", json={
                "document": doc_digits,
                "document_type": doc_type,
            })

    return customer_id


def create_checkout(
    db: Session,
    tenant: Tenant,
    user_email: str,
    user_name: str,
    plan_code: str,
    card_token: str | None = None,
    card_id: str | None = None,
    payment_method: str = "credit_card",
    document: str | None = None,
    billing_address: dict | None = None,
    start_at: str | None = None,
    idempotency_key: str | None = None,
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

    customer_id = _ensure_pagarme_customer(db, tenant, user_email, user_name, document)

    # PIX: cobrança avulsa (Pagar.me não suporta PIX em subscriptions)
    if payment_method == "pix":
        return _checkout_pix(db, tenant, customer_id, plan, idempotency_key)

    # Cartão: cria subscription no Pagar.me
    if not card_token and not card_id:
        raise HTTPException(status_code=422, detail="card_token ou card_id obrigatório para pagamento com cartão")

    final_card_id = card_id

    if card_token:
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
            final_card_id = card_resp.json()["id"]
            # Registra o cartão como pertencente a este tenant
            _register_card_for_tenant(db, tenant.id, final_card_id)

    sub_payload: dict = {
        "customer_id": customer_id,
        "plan_id": plan.pagarme_plan_id,
        "payment_method": "credit_card",
        "card_id": final_card_id,
        # Identifica o tenant no painel do Pagar.me (cada subscription mostra seu estabelecimento)
        "metadata": {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
        },
    }
    if start_at:
        sub_payload["start_at"] = start_at

    headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
    with _pagarme_client() as client:
        resp = client.post("/subscriptions", json=sub_payload, headers=headers)
        print("=== PAGARME SUBSCRIPTION ===")
        print("STATUS:", resp.status_code)
        print("PAYLOAD:", sub_payload)
        print("RESPONSE:", resp.text)
        print("============================")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao criar assinatura no Pagar.me: {resp.text}")

    pagarme_sub = resp.json()

    # Se a assinatura foi criada com status de falha ou inadimplência imediata,
    # significa que o pagamento inicial falhou.
    pagarme_status = pagarme_sub.get("status")
    if pagarme_status in ("failed", "unpaid", "canceled"):
        error_msg = "Pagamento recusado. Por favor, verifique os dados do cartão e tente novamente."
        try:
            charges = pagarme_sub.get("charges", [])
            if charges:
                last_charge = charges[0]
                last_trans = last_charge.get("last_transaction", {})
                acquirer_msg = last_trans.get("acquirer_message")
                gateway_msg = last_trans.get("gateway_response", {}).get("message")
                if acquirer_msg:
                    error_msg = f"Falha no pagamento: {acquirer_msg}"
                elif gateway_msg:
                    error_msg = f"Falha no pagamento: {gateway_msg}"
        except Exception:
            pass
        # Remove any mentions of Pagar.me/Pagarme
        error_msg = error_msg.replace("Pagar.me", "servidor de pagamento").replace("Pagarme", "servidor de pagamento").replace("pagar.me", "servidor de pagamento")
        raise HTTPException(status_code=400, detail=error_msg)

    period_end = datetime.now(timezone.utc) + timedelta(days=30)

    existing = _repo.get_active_by_tenant(db, tenant.id)
    if existing and start_at:
        # Migração PIX→Cartão: período atual já está pago via PIX.
        # Mantém status e current_period_end — só troca o ID e o método.
        _repo.update(db, existing, {
            "pagarme_subscription_id": pagarme_sub["id"],
            "payment_method": "card",
        })
    elif existing:
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


def _checkout_pix(db: Session, tenant: Tenant, customer_id: str, plan: Plan, idempotency_key: str | None = None) -> dict:
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

    headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
    with _pagarme_client() as client:
        resp = client.post("/charges", json=charge_payload, headers=headers)
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
        sub = _repo.update(db, existing, {
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

    expires_at = None
    if pix_data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(pix_data["expires_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    # Cria a cobrança no banco de dados local imediatamente
    _charge_repo.create(
        db=db,
        tenant_id=tenant.id,
        subscription_id=sub.id,
        pagarme_charge_id=charge_id,
        amount=plan.price_cents,
        status="pending",
        payment_method="pix",
        pix_qr_code=pix_data.get("qr_code"),
        pix_qr_code_url=pix_data.get("qr_code_url"),
        expires_at=expires_at,
    )

    db.commit()

    return {
        "pagarme_subscription_id": charge_id,
        "status": "pending",
        "pix_qr_code": pix_data.get("qr_code"),
        "pix_qr_code_url": pix_data.get("qr_code_url"),
        "expires_at": pix_data.get("expires_at"),
    }



def _register_card_for_tenant(db: Session, tenant_id: int, card_id: str) -> None:
    """Garante que o card_id está registrado como pertencente ao tenant no nosso banco."""
    existing = db.query(TenantCard).filter(
        TenantCard.tenant_id == tenant_id,
        TenantCard.pagarme_card_id == card_id,
    ).first()
    if not existing:
        tc = TenantCard(tenant_id=tenant_id, pagarme_card_id=card_id, is_default=False)
        db.add(tc)
        db.flush()


def add_payment_method(
    db: Session,
    tenant: Tenant,
    user_email: str,
    user_name: str,
    card_token: str,
    billing_address: dict | None = None,
    document: str | None = None,
) -> dict:
    customer_id = _ensure_pagarme_customer(db, tenant, user_email, user_name, document)

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
    card_id = card["id"]

    # Registra a posse do cartão neste tenant
    _register_card_for_tenant(db, tenant.id, card_id)
    db.commit()

    return {
        "id": card_id,
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

    # PIX usa cobranças avulsas (charge ID), não subscriptions — não há subscription para cancelar no Pagar.me
    if sub.pagarme_subscription_id and sub.payment_method != "pix":
        with _pagarme_client() as client:
            resp = client.delete(f"/subscriptions/{sub.pagarme_subscription_id}")
            if resp.status_code not in (200, 204):
                raise HTTPException(status_code=502, detail=f"Erro ao cancelar no Pagar.me: {resp.text}")

    return _repo.update(db, sub, {
        "status": "canceled",
        "canceled_at": datetime.now(timezone.utc),
    })


def list_payment_methods(db: Session, tenant: Tenant) -> list[dict]:
    # Busca os card_ids que pertencem especificamente a este tenant
    tenant_card_rows = db.query(TenantCard).filter(
        TenantCard.tenant_id == tenant.id
    ).all()

    if not tenant_card_rows:
        return []

    tenant_card_ids = {tc.pagarme_card_id for tc in tenant_card_rows}
    default_card_ids = {tc.pagarme_card_id for tc in tenant_card_rows if tc.is_default}

    # Se não houver is_default explícito, usa o cartão da assinatura ativa
    if not default_card_ids:
        sub = _repo.get_active_by_tenant(db, tenant.id)
        if sub and sub.pagarme_subscription_id and sub.payment_method != "pix":
            with _pagarme_client() as client:
                sub_resp = client.get(f"/subscriptions/{sub.pagarme_subscription_id}")
                if sub_resp.status_code == 200:
                    active_card_id = sub_resp.json().get("card", {}).get("id")
                    if active_card_id:
                        default_card_ids = {active_card_id}

    if not tenant.pagarme_customer_id:
        return []

    with _pagarme_client() as client:
        resp = client.get(f"/customers/{tenant.pagarme_customer_id}/cards")
        if resp.status_code != 200:
            return []

    all_cards = resp.json().get("data", [])

    # Filtra apenas os cartões que pertencem a este tenant
    return [
        {
            "id": c["id"],
            "brand": c.get("brand", ""),
            "last4": c.get("last_four_digits", ""),
            "exp_month": int(c.get("exp_month", 0)),
            "exp_year": int(c.get("exp_year", 0)),
            "is_default": c["id"] in default_card_ids,
        }
        for c in all_cards
        if c["id"] in tenant_card_ids
    ]


def set_default_payment_method(db: Session, tenant: Tenant, pm_id: str) -> None:
    # Verifica que o cartão pertence a este tenant
    tc = db.query(TenantCard).filter(
        TenantCard.tenant_id == tenant.id,
        TenantCard.pagarme_card_id == pm_id,
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Cartão não encontrado para este estabelecimento")

    # Atualiza is_default na tabela local
    db.query(TenantCard).filter(TenantCard.tenant_id == tenant.id).update({"is_default": False})
    tc.is_default = True
    db.commit()

    # Atualiza também na assinatura do Pagar.me, se houver
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if sub and sub.pagarme_subscription_id and sub.payment_method != "pix":
        with _pagarme_client() as client:
            client.patch(
                f"/subscriptions/{sub.pagarme_subscription_id}/card",
                json={"card_id": pm_id},
            )


def detach_payment_method(db: Session, tenant: Tenant, pm_id: str) -> None:
    # Verifica que o cartão pertence a este tenant
    tc = db.query(TenantCard).filter(
        TenantCard.tenant_id == tenant.id,
        TenantCard.pagarme_card_id == pm_id,
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Cartão não encontrado para este estabelecimento")

    # Remove do nosso banco
    db.delete(tc)
    db.commit()

    # Remove do Pagar.me (best-effort — ignora erro se já foi removido)
    if tenant.pagarme_customer_id:
        with _pagarme_client() as client:
            client.delete(f"/customers/{tenant.pagarme_customer_id}/cards/{pm_id}")


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

        # Subscription webhooks (original)
        if event_type == "subscription.payment_succeeded":
            _on_payment_succeeded(db, event["data"])
        elif event_type == "subscription.payment_failed":
            _on_payment_failed(db, event["data"])
        elif event_type in ("subscription.canceled", "subscription.deactivated"):
            _on_subscription_canceled(db, event["data"])
        elif event_type == "subscription.created":
            _on_subscription_created(db, event["data"])
        elif event_type == "subscription.unpaid":
            _on_subscription_unpaid(db, event["data"])
        elif event_type == "subscription.updated":
            _on_subscription_updated(db, event["data"])

        # Charge webhooks (new/robust)
        elif event_type == "charge.created":
            _on_charge_created(db, event["data"])
        elif event_type == "charge.paid":
            _on_charge_paid(db, event["data"])
        elif event_type in ("charge.payment_failed", "charge.not_authorized"):
            _on_charge_failed(db, event["data"])
        elif event_type == "charge.authorized":
            _on_charge_authorized(db, event["data"])
        elif event_type == "charge.refunded":
            _on_charge_refunded(db, event["data"])
        elif event_type == "charge.voided":
            _on_charge_voided(db, event["data"])
        elif event_type in (
            "charge.with_error",
            "charge.waiting_cancellation",
            "charge.error_on_voiding",
            "charge.error_on_refunding",
        ):
            _on_charge_status_update(db, event["data"], event_type.split(".")[1])

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
    if not sub:
        return

    if sub.status == "active" and data.get("status") == "future":
        return

    _repo.update(db, sub, {"status": _map_status(data.get("status", "pending"))})


def _on_subscription_unpaid(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        _repo.update(db, sub, {"status": "past_due"})


def _on_subscription_updated(db: Session, data: dict) -> None:
    sub_id = data.get("id")
    if not sub_id:
        return

    sub = _repo.get_by_pagarme_subscription_id(db, sub_id)
    if sub:
        update_data = {}
        if "status" in data:
            update_data["status"] = _map_status(data["status"])
        
        if "current_period_end" in data and data["current_period_end"]:
            try:
                dt = datetime.fromisoformat(data["current_period_end"].replace("Z", "+00:00"))
                update_data["current_period_end"] = dt
            except Exception:
                pass
        
        if update_data:
            _repo.update(db, sub, update_data)


def _on_charge_created(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        return

    amount = data.get("amount", 0)
    status = data.get("status", "pending")
    payment_method = data.get("payment_method", "card")
    if payment_method == "credit_card":
        payment_method = "card"

    pagarme_sub_id = data.get("subscription", {}).get("id")
    sub = None
    if pagarme_sub_id:
        sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
    if not sub:
        sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

    if sub:
        pix_data = data.get("last_transaction", {})
        qr_code = pix_data.get("qr_code")
        qr_code_url = pix_data.get("qr_code_url")
        expires_at = None
        if pix_data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(pix_data["expires_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        _charge_repo.create(
            db=db,
            tenant_id=sub.tenant_id,
            subscription_id=sub.id,
            pagarme_charge_id=charge_id,
            amount=amount,
            status=status,
            payment_method=payment_method,
            pix_qr_code=qr_code,
            pix_qr_code_url=qr_code_url,
            expires_at=expires_at,
        )
        db.commit()


def _on_charge_paid(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    amount = data.get("amount", 0)
    status = data.get("status", "paid")
    payment_method = data.get("payment_method", "card")
    if payment_method == "credit_card":
        payment_method = "card"

    pagarme_sub_id = data.get("subscription", {}).get("id")
    sub = None
    if pagarme_sub_id:
        sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
    if not sub:
        sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

    if sub:
        if not charge:
            _charge_repo.create(
                db=db,
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_id,
                amount=amount,
                status=status,
                payment_method=payment_method,
            )
        else:
            _charge_repo.update(db, charge, {"status": status})

        _repo.update(db, sub, {
            "status": "active",
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
        })
        db.commit()


def _on_charge_failed(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    status = data.get("status", "failed")

    pagarme_sub_id = data.get("subscription", {}).get("id")
    sub = None
    if pagarme_sub_id:
        sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
    if not sub:
        sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

    if sub:
        if not charge:
            _charge_repo.create(
                db=db,
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_id,
                amount=data.get("amount", 0),
                status=status,
                payment_method=sub.payment_method,
            )
        else:
            _charge_repo.update(db, charge, {"status": status})

        _repo.update(db, sub, {"status": "past_due"})
        db.commit()


def _on_charge_authorized(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return
    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    status = data.get("status", "authorized_pending_capture")
    pagarme_sub_id = data.get("subscription", {}).get("id")
    sub = None
    if pagarme_sub_id:
        sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
    if sub:
        if not charge:
            _charge_repo.create(
                db=db,
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_id,
                amount=data.get("amount", 0),
                status=status,
                payment_method=sub.payment_method,
            )
        else:
            _charge_repo.update(db, charge, {"status": status})
        db.commit()


def _on_charge_status_update(db: Session, data: dict, status: str) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return
    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": status})
        db.commit()


def _on_charge_refunded(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return
    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": "refunded"})
        db.commit()


def _on_charge_voided(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return
    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": "voided"})
        db.commit()


def list_charges(db: Session, tenant: Tenant) -> list[dict]:
    charges = _charge_repo.list_by_tenant(db, tenant.id)
    return [
        {
            "id": c.pagarme_charge_id,
            "amount": c.amount,
            "status": c.status,
            "payment_method": c.payment_method,
            "pix_qr_code": c.pix_qr_code,
            "pix_qr_code_url": c.pix_qr_code_url,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in charges
    ]


def update_charge_card(
    db: Session,
    tenant: Tenant,
    user_email: str,
    user_name: str,
    charge_id: str,
    card_token: str,
    billing_address: dict | None = None,
    document: str | None = None,
) -> dict:
    customer_id = _ensure_pagarme_customer(db, tenant, user_email, user_name, document)

    addr = billing_address or {
        "country": "BR",
        "state": "SP",
        "city": "São Paulo",
        "zip_code": "01310100",
        "line_1": "Não informado",
    }

    with _pagarme_client() as client:
        card_resp = client.post(
            f"/customers/{customer_id}/cards",
            json={"token": card_token, "billing_address": addr},
        )
        if card_resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao salvar cartão: {card_resp.text}")
        card_id = card_resp.json()["id"]

    payload = {
        "card_id": card_id,
        "update_subscription": True,
        "initiated_type": "retry",
    }
    with _pagarme_client() as client:
        resp = client.patch(
            f"/charges/{charge_id}/card",
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao atualizar cartão da cobrança: {resp.text}")

    charge_data = resp.json()
    status = charge_data.get("status", "failed")

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": status})

    if status in ("paid", "captured", "active"):
        sub = _repo.get_active_by_tenant(db, tenant.id)
        if sub:
            _repo.update(db, sub, {
                "status": "active",
                "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            })
            db.commit()

    return {"status": status}


def retry_charge(db: Session, tenant: Tenant, charge_id: str) -> dict:
    with _pagarme_client() as client:
        resp = client.post(f"/charges/{charge_id}/retry")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao retentar cobrança no Pagar.me: {resp.text}")

    charge_data = resp.json()
    status = charge_data.get("status", "failed")

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": status})

    if status in ("paid", "captured", "active"):
        sub = _repo.get_active_by_tenant(db, tenant.id)
        if sub:
            _repo.update(db, sub, {
                "status": "active",
                "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            })
            db.commit()

    return {"status": status}


def capture_charge(db: Session, tenant: Tenant, charge_id: str) -> dict:
    with _pagarme_client() as client:
        resp = client.post(f"/charges/{charge_id}/capture")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao capturar cobrança no Pagar.me: {resp.text}")

    charge_data = resp.json()
    status = charge_data.get("status", "failed")

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": status})

    if status in ("paid", "captured", "active"):
        sub = _repo.get_active_by_tenant(db, tenant.id)
        if sub:
            _repo.update(db, sub, {
                "status": "active",
                "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            })
            db.commit()

    return {"status": status}


def cancel_charge(db: Session, tenant: Tenant, charge_id: str) -> dict:
    with _pagarme_client() as client:
        resp = client.post(f"/charges/{charge_id}/void")
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao cancelar cobrança no Pagar.me: {resp.text}")

    charge_data = resp.json()
    status = charge_data.get("status", "voided")

    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": status})
        db.commit()

    return {"status": status}

