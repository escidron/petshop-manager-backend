from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy.orm import Session

from app.modules.tenants.models import Tenant
from app.modules.plans.models import Plan
from app.modules.subscriptions.models import Subscription, SubscriptionCharge, TenantCard
from app.modules.subscriptions import service


def test_base_plan_pix_checkout_does_not_double_charge_active_whatsapp_package(db: Session, tenant_id: int):
    """
    Cenário: Período de teste expirou (ou assinatura inativa/pendente).
    O usuário contratou o pacote de WhatsApp via PIX e pagou (R$ 169,90).
    Ao gerar o PIX para pagar o Plano Base ("MONTHLY"), o sistema DEVE cobrar
    apenas o valor do Plano Base (R$ 149,90) e NÃO o valor total do Combo (R$ 319,80),
    evitando a cobrança dupla do pacote.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    now_utc = datetime.now(timezone.utc)
    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="past_due",
        trial_ends_at=now_utc - timedelta(days=2),
        current_period_end=now_utc - timedelta(days=2),
        billing_day=now_utc.day,
        whatsapp_package_id="pkg_2000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=2000,
        whatsapp_messages_used=0,
        whatsapp_period_end=now_utc + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    # Mock Pagar.me client
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": "ch_mock_pix_123",
        "status": "pending",
        "last_transaction": {
            "qr_code": "00020126580014BR.GOV.BCB.PIXmock",
            "qr_code_url": "https://pix.mock/qr",
            "expires_at": (now_utc + timedelta(minutes=30)).isoformat(),
        },
    }

    with patch("app.modules.subscriptions.service._pagarme_client") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.post.return_value = mock_resp
        mock_client.return_value = mock_ctx

        res = service.create_checkout(
            db=db,
            tenant=tenant,
            user_email="test@petshop.com",
            user_name="Test Owner",
            plan_code="MONTHLY",
            payment_method="pix",
        )

    # Verifica que o valor cobrado no PIX é R$ 149,90 (14990 centavos)
    assert res["amount"] == 14990
    assert res["status"] == "pending"
    assert res["charge_id"] == "ch_mock_pix_123"

    # Verifica a cobrança criada no banco
    charge = db.query(SubscriptionCharge).filter(
        SubscriptionCharge.pagarme_charge_id == "ch_mock_pix_123"
    ).first()
    assert charge is not None
    assert charge.amount == 14990

    # Verifica que o plano associado é o MONTHLY
    db.refresh(sub)
    assert sub.plan_id == plan_monthly.id


def test_base_plan_card_checkout_does_not_double_charge_active_whatsapp_package(db: Session, tenant_id: int):
    """
    Cenário: Pacote de WhatsApp já pago (R$ 169,90).
    Ao assinar o Plano Base no Cartão de Crédito, o sistema deve:
    1. Cobrar avulso apenas R$ 149,90 no cartão hoje.
    2. Criar a assinatura Combo no Pagar.me com start_at futuro (próximo vencimento),
       sem cobrar R$ 319,80 hoje.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    db.commit()

    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    now_utc = datetime.now(timezone.utc)
    pkg_end = now_utc + timedelta(days=28)
    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="past_due",
        trial_ends_at=now_utc - timedelta(days=2),
        current_period_end=now_utc - timedelta(days=2),
        billing_day=now_utc.day,
        whatsapp_package_id="pkg_2000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=2000,
        whatsapp_messages_used=0,
        whatsapp_period_end=pkg_end,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    def mock_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        if "/charges" in url:
            resp.json.return_value = {
                "id": "ch_mock_card_single",
                "status": "paid",
                "last_transaction": {"card": {"brand": "visa", "last_four_digits": "1234"}},
            }
        elif "/subscriptions" in url:
            resp.json.return_value = {
                "id": "sub_pagarme_combo_future",
                "status": "active",
                "next_billing_at": pkg_end.isoformat(),
            }
        elif "/customers" in url:
            resp.json.return_value = {"id": "cus_mock_valid_123"}
        return resp

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "cus_mock_valid_123"}
        return resp

    with patch("app.modules.subscriptions.service._pagarme_client") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.post.side_effect = mock_post
        mock_ctx.__enter__.return_value.get.side_effect = mock_get
        mock_client.return_value = mock_ctx

        res = service.create_checkout(
            db=db,
            tenant=tenant,
            user_email="test@petshop.com",
            user_name="Test Owner",
            plan_code="MONTHLY",
            card_id="card_mock_123",
            payment_method="credit_card",
        )

    # Verifica retorno
    assert res["amount"] == 14990
    assert res["status"] == "active"
    assert res["pagarme_subscription_id"] == "sub_pagarme_combo_future"

    # Verifica a cobrança avulsa criada no banco local
    charge = db.query(SubscriptionCharge).filter(
        SubscriptionCharge.pagarme_charge_id == "ch_mock_card_single"
    ).first()
    assert charge is not None
    assert charge.amount == 14990
    assert charge.status == "paid"

    # Verifica que a assinatura local foi ativada como MONTHLY com período alinhado ao pkg_end
    db.refresh(sub)
    assert sub.status == "active"
    assert sub.plan_id == plan_monthly.id
    assert sub.pagarme_subscription_id == "sub_pagarme_combo_future"


def test_renewal_charges_full_combo_when_both_base_and_package_expired(db: Session, tenant_id: int):
    """
    Cenário: Passou o mês de uso.
    Tanto o current_period_end quanto o whatsapp_period_end venceram hoje (ou estão nos últimos 5 dias).
    Ao clicar em gerar PIX (mesmo que o front envie "MONTHLY" ou "combo_1000"),
    o sistema DEVE gerar o PIX com o valor INTEGRAL do Combo (R$ 249,80),
    unificando a renovação do Plano Base + Pacote WhatsApp para o novo mês!
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    now_utc = datetime.now(timezone.utc)
    # Simula ambas as datas vencidas hoje
    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        trial_ends_at=None,
        current_period_end=now_utc - timedelta(hours=2),
        billing_day=now_utc.day,
        whatsapp_package_id="pkg_1000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=968,
        whatsapp_messages_used=450,
        whatsapp_period_end=now_utc - timedelta(hours=2),
        payment_method="pix",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": "ch_mock_combo_renewal",
        "status": "pending",
        "last_transaction": {
            "qr_code": "00020126580014BR.GOV.BCB.PIXmock_combo",
            "qr_code_url": "https://pix.mock/qr_combo",
            "expires_at": (now_utc + timedelta(minutes=30)).isoformat(),
        },
    }

    with patch("app.modules.subscriptions.service._pagarme_client") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.post.return_value = mock_resp
        mock_client.return_value = mock_ctx

        # Front-end pode enviar "MONTHLY"
        res = service.create_checkout(
            db=db,
            tenant=tenant,
            user_email="test@petshop.com",
            user_name="Test Owner",
            plan_code="MONTHLY",
            payment_method="pix",
        )

    # O valor cobrado DEVE ser o do Combo (R$ 249,80 = 24980 centavos)
    assert res["amount"] == 24980
    assert res["status"] == "pending"
    assert res["charge_id"] == "ch_mock_combo_renewal"

    # Confirma que a cobrança foi salva no banco com o valor de 24980
    charge = db.query(SubscriptionCharge).filter(
        SubscriptionCharge.pagarme_charge_id == "ch_mock_combo_renewal"
    ).first()
    assert charge is not None
    assert charge.amount == 24980

    # Agora simula o pagamento desse PIX de renovação
    pay_res = service.simulate_pix_payment(db, tenant)
    assert pay_res["success"] is True

    # Verifica que o período foi estendido por 1 mês e o limite de mensagens foi resetado para 1000
    db.refresh(sub)
    assert sub.status == "active"
    assert sub.current_period_end > now_utc + timedelta(days=20)
    assert sub.whatsapp_period_end == sub.current_period_end
    assert sub.whatsapp_messages_limit == 1000
    assert sub.whatsapp_messages_used == 0


def test_whatsapp_package_downgrade_preview_returns_zero_cents_and_keeps_limit(db: Session, tenant_id: int):
    """
    Cenário: Tenant possui pacote de WhatsApp ativo de maior valor (ex: pkg_1000).
    Ao solicitar preview para um pacote menor (ex: pkg_200):
    - Deve retornar prorated_price_cents = 0 (R$ 0,00).
    - is_downgrade = True.
    - is_prorated = False.
    - Deve preservar a cota atual (1000) no preview.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=now_utc.day,
        current_period_end=now_utc + timedelta(days=20),
        whatsapp_package_id="pkg_1000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=1000,
        whatsapp_messages_used=120,
        whatsapp_period_end=now_utc + timedelta(days=20),
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    preview = service.preview_package_proration(db, tenant, "pkg_200")

    assert preview["is_downgrade"] is True
    assert preview["prorated_price_cents"] == 0
    assert preview["is_prorated"] is False
    assert preview["total_messages"] == 200
    assert preview["prorated_messages"] == 1000
    assert preview["current_package_name"] is not None


def test_whatsapp_package_downgrade_pix_checkout_charges_zero_and_preserves_quota(db: Session, tenant_id: int):
    """
    Cenário: Tenant com pkg_1000 realiza downgrade para pkg_200 via PIX.
    - Não deve cobrar nada hoje (amount = 0).
    - Não deve chamar Pagar.me para gerar cobrança avulsa.
    - Cota de mensagens deve ser mantida intacta (1000) no ciclo vigente.
    - O plano base/combo deve ser atualizado para combo_200 para a próxima renovação.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=now_utc.day,
        current_period_end=now_utc + timedelta(days=20),
        whatsapp_package_id="pkg_1000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=1000,
        whatsapp_messages_used=120,
        whatsapp_period_end=now_utc + timedelta(days=20),
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    res = service.checkout_package(
        db=db,
        tenant=tenant,
        user_email="test@petshop.com",
        user_name="Test Owner",
        package_code="pkg_200",
        payment_method="pix",
    )

    assert res["status"] == "scheduled"
    assert res["amount"] == 0
    assert res["is_downgrade"] is True
    assert res["current_package_id"] == "pkg_1000"
    assert res["next_package_id"] == "pkg_200"

    db.refresh(sub)
    # Pacote ativo DEVE continuar sendo pkg_1000 durante o ciclo vigente!
    assert sub.whatsapp_package_id == "pkg_1000"
    assert sub.whatsapp_next_package_id == "pkg_200"
    assert sub.whatsapp_messages_limit == 1000
    assert sub.whatsapp_messages_used == 120
    assert sub.plan_id == plan_monthly.id

    # Teste de cancelamento do agendamento
    cancel_res = service.cancel_scheduled_downgrade(db, tenant)
    assert cancel_res["success"] is True
    db.refresh(sub)
    assert sub.whatsapp_next_package_id is None
    assert sub.plan_id == plan_monthly.id


def test_switch_from_pix_to_card_creates_future_subscription(db: Session, tenant_id: int):
    """
    Cenário: Tenant pagou via PIX e o período atual está ativo (current_period_end no futuro).
    - Sub pode ter pagarme_subscription_id None ou até legado ch_...
    - Ao cadastrar cartão e chamar set_default_payment_method:
      - Deve identificar que NÃO existe subscription recorrente no Pagar.me.
      - Deve criar a subscription futura agendada (start_at = curr_period_end) sem cobrar agora.
      - Deve salvar a pagarme_subscription_id (sub_...) no banco local.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_test_123"
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)
    future_end = now_utc + timedelta(days=25)

    # Sub com pagamento PIX e charge_id gravado indevidamente anteriormente
    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=future_end.day,
        current_period_end=future_end,
        payment_method="pix",
        pagarme_subscription_id="ch_legacy_pix_charge_123",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    # Registra cartão do tenant
    card_id = "card_test_pix_to_card"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=False,
    )
    db.add(tc)
    db.commit()

    called_post_payload = {}

    def mock_post(url, *args, **kwargs):
        nonlocal called_post_payload
        resp = MagicMock()
        resp.status_code = 201
        if "/subscriptions" in url:
            called_post_payload = kwargs.get("json", {})
            resp.json.return_value = {
                "id": "sub_future_from_pix_switch",
                "status": "future",
                "start_at": called_post_payload.get("start_at"),
            }
        return resp

    with patch("app.modules.subscriptions.service._pagarme_client") as mock_client:
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.post.side_effect = mock_post
        mock_client.return_value = mock_ctx

        service.set_default_payment_method(db, tenant, card_id)

    db.refresh(sub)
    db.refresh(tc)

    # Cartão deve estar ativo como padrão
    assert tc.is_default is True

    # Subscription local deve estar como card e com o ID real sub_... retornado pelo Pagar.me
    assert sub.payment_method == "card"
    assert sub.pagarme_subscription_id == "sub_future_from_pix_switch"
    assert sub.status == "active"

    # Verifica payload enviado para o Pagar.me (puro planless: sem plan_id, com items)
    assert called_post_payload["customer_id"] == "cus_test_123"
    assert called_post_payload["card_id"] == card_id
    assert "plan_id" not in called_post_payload
    assert called_post_payload["interval"] == "month"
    assert called_post_payload["billing_type"] == "prepaid"
    assert len(called_post_payload["items"]) >= 1
    assert called_post_payload["items"][0]["pricing_scheme"]["price"] == 14990
    assert called_post_payload["start_at"] == future_end.strftime("%Y-%m-%dT%H:%M:%SZ")


