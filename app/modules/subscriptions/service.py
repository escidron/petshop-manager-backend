import calendar
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

COMBO_MAP = {
    "pkg_200": "combo_200",
    "pkg_500": "combo_500",
    "pkg_1000": "combo_1000",
    "pkg_2000": "combo_2000",
}


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
                        "name": user_name,
                        "email": user_email,
                        "type": "individual",
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
                "name": user_name,
                "email": user_email,
                "type": "individual",
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
    if plan_code in ("PLAN_MONTHLY", "MONTHLY_PRO", "PRO", "pro"):
        plan_code = "MONTHLY"

    existing_sub = _repo.get_active_by_tenant(db, tenant.id)

    # Se estiver ativando o plano mensal e já tiver pacote de WhatsApp ativo, unifica no Combo
    if plan_code == "MONTHLY" and existing_sub and existing_sub.whatsapp_package_id and existing_sub.whatsapp_package_status == "active":
        combo_code = COMBO_MAP.get(existing_sub.whatsapp_package_id)
        if combo_code:
            combo_plan = db.query(Plan).filter(Plan.code == combo_code, Plan.is_active == True).first()
            if combo_plan and combo_plan.pagarme_plan_id:
                plan_code = combo_code
                if existing_sub.pagarme_whatsapp_subscription_id:
                    try:
                        with _pagarme_client() as client:
                            client.delete(f"/subscriptions/{existing_sub.pagarme_whatsapp_subscription_id}")
                    except Exception as e:
                        print(f"[WARN] Erro ao cancelar assinatura avulsa de WhatsApp: {e}")

    plan: Plan | None = db.query(Plan).filter(Plan.code == plan_code, Plan.is_active == True).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    # Free trial: sem cobrança
    if plan_code == "FREE_TRIAL":
        existing = _repo.get_active_by_tenant(db, tenant.id)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Este estabelecimento já possui ou utilizou o período de gratuidade.",
            )
        trial_ends_at = datetime.now(timezone.utc) + timedelta(days=plan.trial_days or 180)
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

    if payment_method != "pix" and not plan.pagarme_plan_id:
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
    period_end = datetime.now(timezone.utc) + timedelta(days=30)

    existing = _repo.get_active_by_tenant(db, tenant.id)
    if existing and start_at:
        # Migração PIX→Cartão: período atual já está pago via PIX.
        # Mantém status e current_period_end — só troca o ID e o método.
        sub_obj = _repo.update(db, existing, {
            "pagarme_subscription_id": pagarme_sub["id"],
            "payment_method": "card",
        })
    elif existing:
        sub_obj = _repo.update(db, existing, {
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
        sub_obj = _repo.update(db, sub, {"payment_method": "card"})

    # Salva a cobrança inicial do cartão localmente
    sub_obj = sub_obj if 'sub_obj' in locals() else (sub if 'sub' in locals() else existing)
    if sub_obj:
        charges = pagarme_sub.get("charges", [])
        for c in charges:
            charge_id = c.get("id")
            if charge_id:
                amount = c.get("amount", 0)
                status = c.get("status", "pending")
                payment_method = c.get("payment_method", "card")
                if payment_method == "credit_card":
                    payment_method = "card"
                
                last_trans = c.get("last_transaction", {})
                card_data = last_trans.get("card", {})
                card_brand = card_data.get("brand")
                card_last_four = card_data.get("last_four_digits")

                existing_charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
                if not existing_charge:
                    _charge_repo.create(
                        db=db,
                        tenant_id=tenant.id,
                        subscription_id=sub_obj.id,
                        pagarme_charge_id=charge_id,
                        amount=amount,
                        status=status,
                        payment_method=payment_method,
                        card_brand=card_brand,
                        card_last_four=card_last_four,
                    )

    db.commit()

    # Se a assinatura foi criada com status de falha ou inadimplência imediata,
    # significa que o pagamento inicial falhou.
    # Como já salvamos tudo localmente acima, agora podemos levantar a exceção
    # para que o front-end mostre o erro de pagamento, sabendo que a fatura
    # de falha já está registrada no histórico.
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
        "metadata": {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
        },
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
    if charge.get("status") == "failed":
        last_tx = charge.get("last_transaction", {})
        err_msg = "Falha ao gerar cobrança PIX no Pagar.me."
        errors = last_tx.get("gateway_response", {}).get("errors", [])
        if errors:
            err_msg = errors[0].get("message", err_msg)
        raise HTTPException(status_code=400, detail=err_msg)

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
        has_default = db.query(TenantCard).filter(
            TenantCard.tenant_id == tenant_id,
            TenantCard.is_default == True,
        ).first()
        is_default = False if has_default else True

        tc = TenantCard(tenant_id=tenant_id, pagarme_card_id=card_id, is_default=is_default)
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

def is_subscription_eligible_for_refund(db: Session, sub: Subscription) -> bool:
    charge = _charge_repo.get_first_paid_charge(db, sub.id)
    if not charge:
        return False
    
    created_dt = charge.created_at
    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
        
    days_since_payment = (datetime.now(timezone.utc) - created_dt).days
    if days_since_payment > 7:
        return False
        
    # Anti-abuse: check se já teve algum estorno anterior na conta
    has_refund = db.query(SubscriptionCharge).filter(
        SubscriptionCharge.tenant_id == sub.tenant_id,
        SubscriptionCharge.status == 'refunded'
    ).first()
    
    if has_refund:
        return False
        
    return True

def refund_and_cancel_subscription(db: Session, tenant: Tenant) -> Subscription:
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura ativa não encontrada")

    if not is_subscription_eligible_for_refund(db, sub):
        raise HTTPException(status_code=400, detail="Prazo de 7 dias para estorno expirou ou estorno não aplicável.")

    charge = _charge_repo.get_first_paid_charge(db, sub.id)
    if not charge:
        raise HTTPException(status_code=400, detail="Nenhum pagamento encontrado para estornar")

    if charge.pagarme_charge_id and charge.status in ("paid", "captured"):
        with _pagarme_client() as client:
            resp = client.delete(f"/charges/{charge.pagarme_charge_id}")
            if resp.status_code not in (200, 204):
                raise HTTPException(status_code=502, detail=f"Erro ao estornar no Pagar.me: {resp.text}")
        _charge_repo.update(db, charge, {"status": "refunded"})

    return cancel_subscription(db, tenant)


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

def change_subscription_to_pix(db: Session, tenant: Tenant) -> None:
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura ativa não encontrada")
        
    if sub.payment_method == "pix":
        return

    # Se era cartão, cancela a assinatura no Pagar.me para interromper cobranças futuras
    if sub.pagarme_subscription_id and sub.payment_method != "pix":
        with _pagarme_client() as client:
            resp = client.delete(f"/subscriptions/{sub.pagarme_subscription_id}")
            if resp.status_code not in (200, 204, 400, 404):
                raise HTTPException(status_code=502, detail=f"Erro ao cancelar no Pagar.me: {resp.text}")

    _repo.update(db, sub, {"payment_method": "pix"})


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

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Payload inválido: JSON incorreto")

    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Payload inválido: deve ser um objeto JSON")

    event_type = event.get("type", "")
    event_data = event.get("data")

    # Se data for nulo ou não for dicionário, e o tipo de evento exigir processamento, falha
    if event_type and not isinstance(event_data, dict):
        raise HTTPException(status_code=400, detail="Payload inválido: 'data' deve ser um objeto")

    db = SessionLocal()
    try:
        # Subscription webhooks (original)
        if event_type == "subscription.payment_succeeded":
            _on_payment_succeeded(db, event_data)
        elif event_type == "subscription.payment_failed":
            _on_payment_failed(db, event_data)
        elif event_type in ("subscription.canceled", "subscription.deactivated"):
            _on_subscription_canceled(db, event_data)
        elif event_type == "subscription.created":
            _on_subscription_created(db, event_data)
        elif event_type == "subscription.unpaid":
            _on_subscription_unpaid(db, event_data)
        elif event_type == "subscription.updated":
            _on_subscription_updated(db, event_data)

        # Charge webhooks (new/robust)
        elif event_type == "charge.created":
            _on_charge_created(db, event_data)
        elif event_type == "charge.paid":
            _on_charge_paid(db, event_data)
        elif event_type in ("charge.payment_failed", "charge.not_authorized"):
            _on_charge_failed(db, event_data)
        elif event_type == "charge.authorized":
            _on_charge_authorized(db, event_data)
        elif event_type == "charge.refunded":
            _on_charge_refunded(db, event_data)
        elif event_type == "charge.chargedback":
            _on_charge_chargedback(db, event_data)
        elif event_type == "charge.voided":
            _on_charge_voided(db, event_data)
        elif event_type in (
            "charge.with_error",
            "charge.waiting_cancellation",
            "charge.error_on_voiding",
            "charge.error_on_refunding",
        ):
            _on_charge_status_update(db, event_data, event_type.split(".")[1])

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

    metadata_tenant_id = data.get("metadata", {}).get("tenant_id")
    sub = None
    if metadata_tenant_id:
        sub = db.query(Subscription).filter(Subscription.tenant_id == int(metadata_tenant_id)).order_by(Subscription.started_at.desc()).first()

    if not sub:
        pagarme_sub_id = data.get("subscription", {}).get("id") or data.get("subscription_id")
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

        card_data = pix_data.get("card", {})
        card_brand = card_data.get("brand")
        card_last_four = card_data.get("last_four_digits")

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
            card_brand=card_brand,
            card_last_four=card_last_four,
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

    metadata_tenant_id = data.get("metadata", {}).get("tenant_id")
    sub = None
    if metadata_tenant_id:
        sub = db.query(Subscription).filter(Subscription.tenant_id == int(metadata_tenant_id)).order_by(Subscription.started_at.desc()).first()

    if not sub:
        pagarme_sub_id = data.get("subscription", {}).get("id") or data.get("subscription_id")
        if pagarme_sub_id:
            sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
        if not sub:
            sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

    if sub:
        last_trans = data.get("last_transaction", {})
        card_data = last_trans.get("card", {})
        card_brand = card_data.get("brand")
        card_last_four = card_data.get("last_four_digits")

        if not charge:
            _charge_repo.create(
                db=db,
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_id,
                amount=amount,
                status=status,
                payment_method=payment_method,
                card_brand=card_brand,
                card_last_four=card_last_four,
            )
        else:
            _charge_repo.update(db, charge, {
                "status": status,
                "card_brand": card_brand or charge.card_brand,
                "card_last_four": card_last_four or charge.card_last_four,
            })

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

    metadata_tenant_id = data.get("metadata", {}).get("tenant_id")
    sub = None
    if metadata_tenant_id:
        sub = db.query(Subscription).filter(Subscription.tenant_id == int(metadata_tenant_id)).order_by(Subscription.started_at.desc()).first()

    if not sub:
        pagarme_sub_id = data.get("subscription", {}).get("id") or data.get("subscription_id")
        if pagarme_sub_id:
            sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
        if not sub:
            sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

    if sub:
        last_trans = data.get("last_transaction", {})
        card_data = last_trans.get("card", {})
        card_brand = card_data.get("brand")
        card_last_four = card_data.get("last_four_digits")

        if not charge:
            _charge_repo.create(
                db=db,
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_id,
                amount=data.get("amount", 0),
                status=status,
                payment_method=sub.payment_method,
                card_brand=card_brand,
                card_last_four=card_last_four,
            )
        else:
            _charge_repo.update(db, charge, {
                "status": status,
                "card_brand": card_brand or charge.card_brand,
                "card_last_four": card_last_four or charge.card_last_four,
            })

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


def _on_charge_chargedback(db: Session, data: dict) -> None:
    charge_id = data.get("id")
    if not charge_id:
        return
    charge = _charge_repo.get_by_pagarme_charge_id(db, charge_id)
    if charge:
        _charge_repo.update(db, charge, {"status": "chargedback"})
        
        # Bloquear o tenant imediatamente caso tenha tomado chargeback
        sub = _repo.get_by_id(db, charge.subscription_id)
        if sub and sub.status not in ("canceled", "past_due"):
            _repo.update(db, sub, {"status": "past_due"})
            
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


def sync_charges_from_pagarme(db: Session, tenant: Tenant) -> None:
    if not tenant.pagarme_customer_id:
        print(f"[SYNC] Tenant {tenant.id} não possui pagarme_customer_id.")
        return

    print(f"[SYNC] Sincronizando cobranças para Tenant {tenant.id} (Pagar.me Customer: {tenant.pagarme_customer_id})")
    
    # Listar as assinaturas locais do tenant para debug
    local_subs = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).all()
    print(f"[SYNC] Assinaturas locais do Tenant {tenant.id}: {[s.pagarme_subscription_id for s in local_subs]}")

    try:
        with _pagarme_client() as client:
            resp = client.get(f"/charges?customer_id={tenant.pagarme_customer_id}")
            print(f"[SYNC] Resposta do Pagar.me status: {resp.status_code}")
            if resp.status_code == 200:
                charges_data = resp.json().get("data", [])
                print(f"[SYNC] Total de cobranças retornadas pelo Pagar.me: {len(charges_data)}")
                for c in charges_data:
                    charge_id = c.get("id")
                    if not charge_id:
                        continue

                    existing = _charge_repo.get_by_pagarme_charge_id(db, charge_id)

                    # Tentar identificar o tenant através do metadata da charge
                    metadata_tenant_id = c.get("metadata", {}).get("tenant_id")
                    
                    charge_sub = None
                    if metadata_tenant_id:
                        if str(metadata_tenant_id) != str(tenant.id):
                            # Pertence a outro tenant, remove se já existia localmente
                            if existing:
                                print(f"[SYNC] Removendo charge desassociada {charge_id} do tenant {tenant.id}")
                                db.delete(existing)
                            continue
                        
                        # Se o tenant_id bate com o atual, localiza a subscription correspondente
                        pagarme_sub_id = c.get("subscription", {}).get("id") or c.get("subscription_id")
                        if pagarme_sub_id:
                            charge_sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
                        if not charge_sub:
                            # Fallback para PIX ou se a sub não foi achada pelo ID mas sabemos que o tenant é este
                            charge_sub = _repo.get_by_pagarme_subscription_id(db, charge_id)
                        if not charge_sub:
                            charge_sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).order_by(Subscription.started_at.desc()).first()
                    else:
                        # Fallback antigo caso não haja metadata
                        pagarme_sub_id = c.get("subscription", {}).get("id") or c.get("subscription_id")
                        if pagarme_sub_id:
                            charge_sub = _repo.get_by_pagarme_subscription_id(db, pagarme_sub_id)
                        if not charge_sub:
                            charge_sub = _repo.get_by_pagarme_subscription_id(db, charge_id)

                    print(f"[SYNC] Charge {charge_id} -> Sub encontrada localmente: {charge_sub.id if charge_sub else 'NENHUMA'} (Tenant da Sub: {charge_sub.tenant_id if charge_sub else 'N/A'})")

                    # Se a assinatura não existe no banco ou pertence a outro tenant, ignora e limpa se já existia localmente
                    if not charge_sub or charge_sub.tenant_id != tenant.id:
                        if existing:
                            print(f"[SYNC] Removendo charge desassociada {charge_id}")
                            db.delete(existing)
                        continue
                    
                    amount = c.get("amount", 0)
                    status = c.get("status", "pending")
                    payment_method = c.get("payment_method", "card")
                    if payment_method == "credit_card":
                        payment_method = "card"
                    
                    last_trans = c.get("last_transaction", {})
                    pix_qr_code = last_trans.get("qr_code")
                    pix_qr_code_url = last_trans.get("qr_code_url")
                    expires_at = None
                    if last_trans.get("expires_at"):
                        try:
                            expires_at = datetime.fromisoformat(last_trans["expires_at"].replace("Z", "+00:00"))
                        except Exception:
                            pass
                            
                    card_data = last_trans.get("card", {})
                    card_brand = card_data.get("brand")
                    card_last_four = card_data.get("last_four_digits")

                    if not existing:
                        print(f"[SYNC] Criando nova cobrança local {charge_id} para Tenant {tenant.id}")
                        _charge_repo.create(
                            db=db,
                            tenant_id=tenant.id,
                            subscription_id=charge_sub.id,
                            pagarme_charge_id=charge_id,
                            amount=amount,
                            status=status,
                            payment_method=payment_method,
                            pix_qr_code=pix_qr_code,
                            pix_qr_code_url=pix_qr_code_url,
                            expires_at=expires_at,
                            card_brand=card_brand,
                            card_last_four=card_last_four,
                        )
                    else:
                        # Se já existe, atualiza os dados e garante que o tenant_id está correto
                        print(f"[SYNC] Atualizando cobrança local {charge_id}")
                        _charge_repo.update(db, existing, {
                            "tenant_id": tenant.id,
                            "subscription_id": charge_sub.id,
                            "status": status,
                            "card_brand": card_brand or existing.card_brand,
                            "card_last_four": card_last_four or existing.card_last_four,
                        })
                db.commit()
    except Exception as e:
        print(f"Error syncing charges from Pagar.me: {e}")


def list_charges(db: Session, tenant: Tenant) -> list[dict]:
    # Sincroniza faturas diretamente da API do Pagar.me para garantir integridade local
    sync_charges_from_pagarme(db, tenant)

    charges = _charge_repo.list_by_tenant(db, tenant.id)
    return [
        {
            "id": c.pagarme_charge_id,
            "amount": c.amount,
            "status": c.status,
            "payment_method": c.payment_method,
            "card_brand": c.card_brand,
            "card_last_four": c.card_last_four,
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


PACKAGE_LIMITS = {
    "pkg_200": 200,
    "pkg_500": 500,
    "pkg_1000": 1000,
    "pkg_2000": 2000,
}


def calculate_proration(billing_day: int, price_cents: int, total_messages: int = 0, now: datetime | None = None) -> dict:
    """
    Calcula o valor pro-rata e a próxima data de cobrança mensal baseada no billing_day.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    current_day = now.day
    current_year = now.year
    current_month = now.month

    # Quantidade de dias no mês atual
    _, days_in_current_month = calendar.monthrange(current_year, current_month)

    # Se hoje é exatamente o dia de cobrança (billing_day)
    if current_day == billing_day:
        if current_month == 12:
            next_year = current_year + 1
            next_month = 1
        else:
            next_year = current_year
            next_month = current_month + 1

        _, days_in_next_month = calendar.monthrange(next_year, next_month)
        actual_day = min(billing_day, days_in_next_month)
        next_billing_date = datetime(next_year, next_month, actual_day, now.hour, now.minute, now.second, tzinfo=timezone.utc)

        return {
            "prorated_amount_cents": price_cents,
            "monthly_amount_cents": price_cents,
            "prorated_messages": total_messages,
            "total_messages": total_messages,
            "days_remaining": days_in_current_month,
            "total_days_in_cycle": days_in_current_month,
            "next_billing_date": next_billing_date,
            "is_prorated": False,
        }

    # Se hoje é ANTES do billing_day no mesmo mês (ex: hoje dia 10, billing dia 24)
    if current_day < billing_day:
        days_remaining = billing_day - current_day
        actual_day = min(billing_day, days_in_current_month)
        next_billing_date = datetime(current_year, current_month, actual_day, 12, 0, 0, tzinfo=timezone.utc)
    else:
        # Se hoje é DEPOIS do billing_day (ex: hoje dia 24, billing dia 01)
        if current_month == 12:
            next_year = current_year + 1
            next_month = 1
        else:
            next_year = current_year
            next_month = current_month + 1

        _, days_in_next_month = calendar.monthrange(next_year, next_month)
        actual_day = min(billing_day, days_in_next_month)
        next_billing_date = datetime(next_year, next_month, actual_day, 12, 0, 0, tzinfo=timezone.utc)

        days_remaining = (days_in_current_month - current_day) + actual_day

    # Cálculo pro-rata de valor e de limite de mensagens
    prorated_amount_cents = max(100, round((price_cents / days_in_current_month) * days_remaining))
    prorated_messages = max(1, round((total_messages / days_in_current_month) * days_remaining)) if total_messages > 0 else total_messages

    return {
        "prorated_amount_cents": prorated_amount_cents,
        "monthly_amount_cents": price_cents,
        "prorated_messages": prorated_messages,
        "total_messages": total_messages,
        "days_remaining": days_remaining,
        "total_days_in_cycle": days_in_current_month,
        "next_billing_date": next_billing_date,
        "is_prorated": True,
    }


def preview_package_proration(db: Session, tenant: Tenant, package_code: str) -> dict:
    if not package_code.startswith("pkg_"):
        package_code = f"pkg_{package_code}"

    plan = db.query(Plan).filter(Plan.code == package_code, Plan.is_active == True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Pacote não encontrado")

    sub = _repo.get_active_by_tenant(db, tenant.id)
    billing_day = sub.billing_day if (sub and sub.billing_day) else datetime.now(timezone.utc).day

    limit = PACKAGE_LIMITS.get(package_code, 500)
    proration = calculate_proration(billing_day, plan.price_cents, total_messages=limit)

    return {
        "package_code": package_code,
        "package_name": plan.name,
        "monthly_price_cents": plan.price_cents,
        "prorated_price_cents": proration["prorated_amount_cents"],
        "prorated_messages": proration["prorated_messages"],
        "total_messages": limit,
        "billing_day": billing_day,
        "days_remaining": proration["days_remaining"],
        "total_days_in_cycle": proration["total_days_in_cycle"],
        "next_billing_date": proration["next_billing_date"].isoformat(),
        "is_prorated": proration["is_prorated"],
    }


def checkout_package(
    db: Session,
    tenant: Tenant,
    user_email: str,
    user_name: str,
    package_code: str,
    payment_method: str = "credit_card",
    card_token: str | None = None,
    card_id: str | None = None,
    document: str | None = None,
    billing_address: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    if not package_code.startswith("pkg_"):
        package_code = f"pkg_{package_code}"

    plan = db.query(Plan).filter(Plan.code == package_code, Plan.is_active == True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Pacote não encontrado")

    if not plan.pagarme_plan_id:
        raise HTTPException(status_code=422, detail="Este pacote não possui ID configurado no Pagar.me")

    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub:
        raise HTTPException(status_code=400, detail="Nenhuma assinatura base encontrada")

    limit = PACKAGE_LIMITS.get(package_code, 500)
    billing_day = sub.billing_day or datetime.now(timezone.utc).day
    proration = calculate_proration(billing_day, plan.price_cents, total_messages=limit)
    prorated_amount = proration["prorated_amount_cents"]
    next_billing_date = proration["next_billing_date"]
    is_prorated = proration["is_prorated"]
    initial_messages_limit = proration["prorated_messages"] if is_prorated else limit

    customer_id = _ensure_pagarme_customer(db, tenant, user_email, user_name, document)

    # PIX
    if payment_method == "pix":
        charge_payload = {
            "customer_id": customer_id,
            "amount": prorated_amount,
            "payment": {
                "payment_method": "pix",
                "pix": {
                    "expires_in": 86400,
                },
            },
            "metadata": {
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "type": "whatsapp_package_proration" if is_prorated else "whatsapp_package",
                "package_code": package_code,
            },
        }

        headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
        with _pagarme_client() as client:
            resp = client.post("/charges", json=charge_payload, headers=headers)
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=502, detail=f"Erro ao gerar PIX para pacote: {resp.text}")

        charge = resp.json()
        charge_id = charge["id"]
        pix_data = charge.get("last_transaction", {})
        expires_at = None
        if pix_data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(pix_data["expires_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        _charge_repo.create(
            db=db,
            tenant_id=tenant.id,
            subscription_id=sub.id,
            pagarme_charge_id=charge_id,
            amount=prorated_amount,
            status="pending",
            payment_method="pix",
            pix_qr_code=pix_data.get("qr_code"),
            pix_qr_code_url=pix_data.get("qr_code_url"),
            expires_at=expires_at,
        )

        _repo.update(db, sub, {
            "whatsapp_package_id": package_code,
            "whatsapp_package_status": "pending_payment",
            "whatsapp_messages_limit": initial_messages_limit,
        })
        db.commit()

        return {
            "status": "pending",
            "payment_method": "pix",
            "amount": prorated_amount,
            "pix_qr_code": pix_data.get("qr_code"),
            "pix_qr_code_url": pix_data.get("qr_code_url"),
            "expires_at": pix_data.get("expires_at"),
            "next_billing_date": next_billing_date.isoformat(),
        }

    # Cartão de Crédito
    if not card_token and not card_id:
        raise HTTPException(status_code=422, detail="card_token ou card_id obrigatório para pagamento com cartão")

    final_card_id = card_id
    if card_token:
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
            _register_card_for_tenant(db, tenant.id, final_card_id)

    # 1. Se for pro-rata, cobra o valor avulso agora
    if is_prorated:
        charge_payload = {
            "customer_id": customer_id,
            "amount": prorated_amount,
            "payment": {
                "payment_method": "credit_card",
                "credit_card": {
                    "card_id": final_card_id,
                    "statement_descriptor": "PETCONTROLE",
                    "installments": 1,
                },
            },
            "metadata": {
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "type": "whatsapp_package_proration",
                "package_code": package_code,
            },
        }
        with _pagarme_client() as client:
            charge_resp = client.post("/charges", json=charge_payload)
            if charge_resp.status_code not in (200, 201):
                raise HTTPException(status_code=502, detail=f"Erro ao processar cobrança proporcional: {charge_resp.text}")
            charge_data = charge_resp.json()
            if charge_data.get("status") not in ("paid", "active", "pending"):
                raise HTTPException(status_code=400, detail="Pagamento do pacote recusado pela operadora do cartão")

            last_trans = charge_data.get("last_transaction", {})
            card_info = last_trans.get("card", {})
            _charge_repo.create(
                db=db,
                tenant_id=tenant.id,
                subscription_id=sub.id,
                pagarme_charge_id=charge_data["id"],
                amount=prorated_amount,
                status=charge_data.get("status", "paid"),
                payment_method="card",
                card_brand=card_info.get("brand"),
                card_last_four=card_info.get("last_four_digits"),
            )

    # Verifica se a assinatura base do tenant está em período de gratuidade (trial) ativo
    is_base_trial_active = (
        (sub.plan and sub.plan.code == "FREE_TRIAL")
        or (sub.status == "trialing" and sub.trial_ends_at and sub.trial_ends_at > datetime.now(timezone.utc))
    )

    # Se a assinatura base for PAGA (não trial ativo), usa o Plano Combo para unificar em uma única assinatura no Pagar.me
    combo_plan = None
    if not is_base_trial_active:
        combo_code = COMBO_MAP.get(package_code)
        if combo_code:
            combo_plan = db.query(Plan).filter(Plan.code == combo_code, Plan.is_active == True).first()

    target_pagarme_plan_id = combo_plan.pagarme_plan_id if (combo_plan and combo_plan.pagarme_plan_id) else plan.pagarme_plan_id
    target_plan_id = combo_plan.id if combo_plan else sub.plan_id

    # 2. Cancela assinaturas anteriores no Pagar.me para manter apenas UMA assinatura unificada
    if combo_plan and sub.pagarme_subscription_id:
        try:
            with _pagarme_client() as client:
                client.delete(f"/subscriptions/{sub.pagarme_subscription_id}")
        except Exception as e:
            print(f"[WARN] Erro ao cancelar assinatura base anterior para unificação em combo: {e}")

    if sub.pagarme_whatsapp_subscription_id:
        try:
            with _pagarme_client() as client:
                client.delete(f"/subscriptions/{sub.pagarme_whatsapp_subscription_id}")
        except Exception as e:
            print(f"[WARN] Erro ao cancelar assinatura anterior de pacote no Pagar.me: {e}")

    # 3. Cria a assinatura no Pagar.me com start_at
    sub_payload = {
        "customer_id": customer_id,
        "plan_id": target_pagarme_plan_id,
        "payment_method": "credit_card",
        "card_id": final_card_id,
        "metadata": {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "type": "combo_subscription" if combo_plan else "whatsapp_package",
            "package_code": package_code,
        },
    }
    if is_prorated:
        sub_payload["start_at"] = next_billing_date.isoformat()

    with _pagarme_client() as client:
        sub_resp = client.post("/subscriptions", json=sub_payload)
        if sub_resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Erro ao criar assinatura no Pagar.me: {sub_resp.text}")
        pagarme_sub = sub_resp.json()

    # Se não foi pro-rata (cobrança imediata da assinatura), salva a cobrança
    if not is_prorated:
        charges = pagarme_sub.get("charges", [])
        for c in charges:
            charge_id = c.get("id")
            if charge_id:
                last_trans = c.get("last_transaction", {})
                card_info = last_trans.get("card", {})
                _charge_repo.create(
                    db=db,
                    tenant_id=tenant.id,
                    subscription_id=sub.id,
                    pagarme_charge_id=charge_id,
                    amount=c.get("amount", (combo_plan or plan).price_cents),
                    status=c.get("status", "paid"),
                    payment_method="card",
                    card_brand=card_info.get("brand"),
                    card_last_four=card_info.get("last_four_digits"),
                )

    # 3. Atualiza dados locais
    update_data = {
        "whatsapp_package_id": package_code,
        "whatsapp_package_status": "active",
        "whatsapp_messages_limit": initial_messages_limit,
        "whatsapp_messages_used": 0,
        "whatsapp_period_end": next_billing_date,
        "payment_method": "card",
    }
    if combo_plan:
        update_data["plan_id"] = combo_plan.id
        update_data["pagarme_subscription_id"] = pagarme_sub["id"]
        update_data["pagarme_whatsapp_subscription_id"] = None
    else:
        update_data["pagarme_whatsapp_subscription_id"] = pagarme_sub["id"]

    _repo.update(db, sub, update_data)
    db.commit()

    return {
        "status": "active",
        "package_code": package_code,
        "messages_limit": initial_messages_limit,
        "next_billing_date": next_billing_date.isoformat(),
        "pagarme_subscription_id": pagarme_sub["id"],
    }


def cancel_package(db: Session, tenant: Tenant) -> dict:
    sub = _repo.get_active_by_tenant(db, tenant.id)
    if not sub or not sub.whatsapp_package_id:
        raise HTTPException(status_code=400, detail="Nenhum pacote ativo para cancelar")

    # Se estiver em plano combo, cancela o combo e recria a assinatura MONTHLY no Pagar.me
    if sub.plan and sub.plan.code.startswith("combo_"):
        if sub.pagarme_subscription_id:
            try:
                with _pagarme_client() as client:
                    client.delete(f"/subscriptions/{sub.pagarme_subscription_id}")
            except Exception as e:
                print(f"[WARN] Erro ao cancelar assinatura combo no Pagar.me: {e}")

        monthly_plan = db.query(Plan).filter(Plan.code == "MONTHLY", Plan.is_active == True).first()
        if monthly_plan and monthly_plan.pagarme_plan_id and tenant.pagarme_customer_id:
            cards = list_payment_methods(db, tenant)
            card_id = cards[0]["id"] if cards else None
            if card_id:
                next_start = sub.whatsapp_period_end or sub.current_period_end or (datetime.now(timezone.utc) + timedelta(days=30))
                monthly_payload = {
                    "customer_id": tenant.pagarme_customer_id,
                    "plan_id": monthly_plan.pagarme_plan_id,
                    "payment_method": "credit_card",
                    "card_id": card_id,
                    "start_at": next_start.isoformat(),
                    "metadata": {
                        "tenant_id": str(tenant.id),
                        "tenant_name": tenant.name,
                    },
                }
                with _pagarme_client() as client:
                    m_resp = client.post("/subscriptions", json=monthly_payload)
                    if m_resp.status_code in (200, 201):
                        new_sub_data = m_resp.json()
                        _repo.update(db, sub, {
                            "plan_id": monthly_plan.id,
                            "pagarme_subscription_id": new_sub_data["id"],
                            "whatsapp_package_id": None,
                            "whatsapp_package_status": "canceled",
                            "pagarme_whatsapp_subscription_id": None,
                        })
                        db.commit()
                        return {"status": "canceled", "message": "Pacote cancelado e assinatura revertida para Plano Mensal (R$ 99,90/mês)"}

    if sub.pagarme_whatsapp_subscription_id:
        try:
            with _pagarme_client() as client:
                client.delete(f"/subscriptions/{sub.pagarme_whatsapp_subscription_id}")
        except Exception as e:
            print(f"[WARN] Erro ao cancelar assinatura do pacote no Pagar.me: {e}")

    _repo.update(db, sub, {
        "whatsapp_package_status": "canceled",
        "pagarme_whatsapp_subscription_id": None,
    })
    db.commit()

    return {"status": "canceled", "message": "Pacote cancelado com sucesso"}

