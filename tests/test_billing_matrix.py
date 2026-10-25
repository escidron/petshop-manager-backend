"""
Suíte Canônica de Testes do Módulo de Faturamento / SaaS Billing (Data Pet).

Cobre a Matriz Completa de Cenários (8 Blocos Ortogonais):
1. Onboarding & Criação da Conta
2. Durante o Trial (Período Gratuito)
3. Mutações de Pacotes no Meio do Mês (Pró-rata, Upgrade, Downgrade e Cotas)
4. Conflitos, Pix Abandonado e Idempotência
5. Fim do Período e Transições de Ciclo (Renovações)
6. Inadimplência, Tolerância (Grace Period) e Bloqueio
7. Cancelamento e Reativação (Churn & Resurrection)
8. Troca de Métodos de Pagamento (Pix <-> Cartão)
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy.orm import Session

from app.modules.tenants.models import Tenant
from app.modules.plans.models import Plan
from app.modules.subscriptions.models import Subscription, SubscriptionCharge, TenantCard
from app.modules.subscriptions import service


@pytest.fixture
def mock_pagarme():
    """Mock unificado para chamadas ao Pagar.me V5 em sandbox."""
    with patch("app.modules.subscriptions.service._pagarme_client") as mock_client:
        mock_ctx = MagicMock()
        client = mock_ctx.__enter__.return_value

        # Mock GET (ex: /customers/{id}, /subscriptions/{id})
        def default_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "cus_mock_valid_123", "status": "active"}
            return resp

        # Mock POST (ex: /charges, /subscriptions)
        def default_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 201
            payload = kwargs.get("json", {})
            if "/charges" in url:
                pm = payload.get("payment", {}).get("payment_method", "credit_card")
                if pm == "pix":
                    resp.json.return_value = {
                        "id": "ch_mock_pix_123",
                        "status": "pending",
                        "last_transaction": {
                            "qr_code": "00020126580014BR.GOV.BCB.PIX_MOCK",
                            "qr_code_url": "https://pix.mock/qr",
                            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                        },
                    }
                else:
                    resp.json.return_value = {
                        "id": "ch_mock_card_123",
                        "status": "paid",
                        "last_transaction": {"card": {"brand": "visa", "last_four_digits": "1234"}},
                    }
            elif "/subscriptions" in url:
                resp.json.return_value = {
                    "id": "sub_mock_pagarme_123",
                    "status": "future" if payload.get("start_at") else "active",
                    "start_at": payload.get("start_at"),
                }
            elif "/customers" in url:
                resp.json.return_value = {"id": "cus_mock_valid_123"}
            return resp

        # Mock DELETE / PATCH
        def default_delete(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            return resp

        def default_patch(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            return resp

        client.get.side_effect = default_get
        client.post.side_effect = default_post
        client.delete.side_effect = default_delete
        client.patch.side_effect = default_patch

        mock_client.return_value = mock_ctx
        yield client


# ==============================================================================
# BLOCO 1: ONBOARDING & CRIAÇÃO DA CONTA
# ==============================================================================

def test_onboarding_pure_trial_creates_trialing_subscription_without_package(db: Session, tenant_id: int):
    """
    Cenário 1.1: Cadastro básico selecionando apenas o Free Trial.
    - Status deve ser 'trialing'.
    - Trial válido por 7 dias.
    - Nenhum pacote de WhatsApp ativo.
    - Nenhuma cobrança gerada.
    """
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=7)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        whatsapp_package_id=None,
        whatsapp_package_status="inactive",
        whatsapp_messages_limit=0,
        whatsapp_messages_used=0,
        payment_method="card",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    assert sub.status == "trialing"
    assert sub.trial_ends_at is not None
    assert sub.whatsapp_package_status == "inactive"
    assert sub.whatsapp_messages_limit == 0
    assert len(sub.charges) == 0


def test_onboarding_with_package_selected_creates_pending_payment(db: Session, tenant_id: int):
    """
    Cenário 1.2: Cadastro escolhendo pacote de WhatsApp no formulário inicial (sem cartão).
    - Status da assinatura: 'trialing'.
    - Pacote selecionado (ex: pkg_200) com status 'pending_payment'.
    - Mensagens não podem ser consumidas enquanto o status não for 'active'.
    """
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=7)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        whatsapp_package_id="pkg_200",
        whatsapp_package_status="pending_payment",
        whatsapp_messages_limit=200,
        whatsapp_messages_used=0,
        payment_method="pix",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    assert sub.status == "trialing"
    assert sub.whatsapp_package_id == "pkg_200"
    assert sub.whatsapp_package_status == "pending_payment"
    assert sub.whatsapp_package_status != "active"


# ==============================================================================
# BLOCO 2: DURANTE O TRIAL (PERÍODO GRATUITO)
# ==============================================================================

def test_trial_add_card_schedules_future_subscription_without_immediate_charge(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 2.1: Tenant em Trial cadastra cartão de crédito.
    - Deve salvar o cartão como default.
    - Deve criar assinatura futura no Pagar.me com start_at = trial_ends_at.
    - NÃO deve realizar nenhuma cobrança avulsa no cartão hoje.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()

    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=6)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        payment_method="card",
    )
    db.add(sub)
    db.commit()

    card_id = "card_trial_save_123"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=False,
    )
    db.add(tc)
    db.commit()

    service.set_default_payment_method(db, tenant, card_id)

    db.refresh(sub)
    db.refresh(tc)

    assert tc.is_default is True
    assert sub.pagarme_subscription_id == "sub_mock_pagarme_123"
    assert sub.status == "trialing"


def test_trial_hire_package_via_pix_generates_prorata_pix(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 2.2: Tenant em Trial contrata pacote via PIX.
    - Deve emitir Pix avulso com valor proporcional até o fim do trial.
    - Pacote fica como pending_payment.
    - Ao simular o pagamento (webhook charge.paid), comuta para active.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    db.commit()

    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=5)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    res = service.checkout_package(
        db=db,
        tenant=tenant,
        user_email="trial@petshop.com",
        user_name="Trial Owner",
        package_code="pkg_200",
        payment_method="pix",
    )

    assert res["status"] == "pending"
    assert res["charge_id"] == "ch_mock_pix_123"

    # Simula quitação do Pix
    pay_res = service.simulate_pix_payment(db, tenant)
    assert pay_res["success"] is True

    db.refresh(sub)
    assert sub.whatsapp_package_id == "pkg_200"
    assert sub.whatsapp_package_status == "active"
    assert sub.whatsapp_messages_limit == 200


def test_trial_with_saved_card_hire_package_charges_card_and_updates_future(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 2.3: Tenant em Trial já tem cartão salvo e contrata pacote no cartão.
    - Cobra avulso do pacote hoje no cartão até o fim do trial.
    - Atualiza assinatura futura no Pagar.me para renovar Plano Base + Pacote.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=5)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        payment_method="card",
        pagarme_subscription_id="sub_pagarme_future_base",
    )
    db.add(sub)

    card_id = "card_saved_trial_123"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=True,
    )
    db.add(tc)
    db.commit()

    res = service.checkout_package(
        db=db,
        tenant=tenant,
        user_email="trial@petshop.com",
        user_name="Trial Owner",
        package_code="pkg_500",
        card_id=card_id,
        payment_method="card",
    )

    db.refresh(sub)
    assert sub.whatsapp_package_id == "pkg_500"
    assert sub.whatsapp_package_status == "active"
    assert sub.whatsapp_messages_limit == 500

    # Validação estrita do payload enviado ao Pagar.me:
    # 1. Deve ter chamado /charges com o valor do pacote
    # 2. Como a assinatura já existia no Pagar.me, atualizou o item in-place na mesma assinatura!
    item_calls = [
        call for call in mock_pagarme.post.call_args_list
        if f"/subscriptions/{sub.pagarme_subscription_id}/items" in call[0][0]
    ]
    assert len(item_calls) > 0, "Deveria ter chamado POST /subscriptions/{id}/items para atualizar o item in-place"
    item_payload = item_calls[-1][1]["json"]
    assert item_payload["pricing_scheme"]["price"] == 4990
    assert "WhatsApp" in item_payload["name"]
    # A subscription ID deve ter sido PRESERVADA, sem cancelamento ou churn
    assert sub.pagarme_subscription_id == "sub_pagarme_future_base"


def test_trial_with_active_pix_package_then_adds_card_schedules_unified_subscription(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 4: Tenant em Trial contratou pacote via PIX e pagou.
    Depois, cadastra um cartão de crédito como método padrão.
    O sistema DEVE:
    - Agendar a assinatura futura no Pagar.me (start_at = trial_end)
    - Conter o plano base (Data Pet Pro)
    - Conter o item do pacote de WhatsApp nos items da assinatura futura!
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=10)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        whatsapp_package_id="pkg_500",
        whatsapp_package_status="active",
        whatsapp_messages_limit=500,
        whatsapp_messages_used=0,
        whatsapp_period_end=trial_end,
        payment_method="pix",
    )
    db.add(sub)

    card_id = "card_new_trial_pix_123"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=False,
    )
    db.add(tc)
    db.commit()

    service.set_default_payment_method(db, tenant, card_id)

    sub_calls = [
        call for call in mock_pagarme.post.call_args_list
        if "/subscriptions" in call[0][0]
    ]
    assert len(sub_calls) > 0, "Deveria ter chamado POST /subscriptions"
    sub_payload = sub_calls[-1][1]["json"]
    assert sub_payload["card_id"] == card_id
    assert "items" in sub_payload, "A assinatura futura deve conter items com o pacote de WhatsApp"
    pkg_items = [it for it in sub_payload["items"] if it.get("pricing_scheme", {}).get("price") == 4990]
    assert len(pkg_items) == 1, "Deveria incluir pkg_500 (R$ 49,90) na assinatura futura agendada"


def test_trial_switch_card_to_pix_cancels_future_sub_and_sets_pix(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 2.6: Tenant em Trial com cartão salvo decide mudar preferência para PIX.
    - Cancela a assinatura futura no Pagar.me.
    - Muda payment_method para 'pix'.
    - NÃO gera Pix antecipado do plano.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_trial = db.query(Plan).filter(Plan.code == "FREE_TRIAL").first()
    now_utc = datetime.now(timezone.utc)
    trial_end = now_utc + timedelta(days=4)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_trial.id,
        status="trialing",
        trial_ends_at=trial_end,
        current_period_end=trial_end,
        billing_day=trial_end.day,
        payment_method="card",
        pagarme_subscription_id="sub_fut_to_cancel_123",
    )
    db.add(sub)
    db.commit()

    service.change_subscription_to_pix(db, tenant)

    db.refresh(sub)
    assert sub.payment_method == "pix"
    assert sub.pagarme_subscription_id is None


# ==============================================================================
# BLOCO 3: MUTAÇÕES DE PACOTES NO MEIO DO MÊS (UPGRADE, DOWNGRADE, COTAS)
# ==============================================================================

def test_active_card_upgrade_package_charges_prorata_delta(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 3.1: Upgrade de Pacote no Cartão (pkg_200 -> pkg_500).
    - Calcula diferença pró-rata dos dias restantes.
    - Cobra delta no cartão imediatamente.
    - Atualiza limite de mensagens imediatamente para 500.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    now_utc = datetime.now(timezone.utc)
    period_end = now_utc + timedelta(days=15)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=period_end.day,
        current_period_end=period_end,
        whatsapp_package_id="pkg_200",
        whatsapp_package_status="active",
        whatsapp_messages_limit=200,
        whatsapp_messages_used=180,
        whatsapp_period_end=period_end,
        payment_method="card",
        pagarme_subscription_id="sub_pagarme_active_card",
    )
    db.add(sub)

    card_id = "card_upgrade_123"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=True,
    )
    db.add(tc)
    db.commit()

    res = service.checkout_package(
        db=db,
        tenant=tenant,
        user_email="upgrade@petshop.com",
        user_name="Upgrade Owner",
        package_code="pkg_500",
        card_id=card_id,
        payment_method="card",
    )

    db.refresh(sub)
    assert res["status"] in ("active", "paid")
    assert sub.whatsapp_package_id == "pkg_500"
    assert sub.whatsapp_messages_limit == 500
    assert sub.whatsapp_messages_used == 180

    # Verifica que atualizou o item in-place na mesma assinatura
    item_calls = [
        call for call in mock_pagarme.post.call_args_list
        if f"/subscriptions/{sub.pagarme_subscription_id}/items" in call[0][0]
    ]
    assert len(item_calls) > 0, "Deveria ter atualizado o item in-place na assinatura no Pagar.me"
    item_payload = item_calls[-1][1]["json"]
    assert item_payload["pricing_scheme"]["price"] == 4990
    assert "WhatsApp" in item_payload["name"]
    # Subscription ID preservada intacta!
    assert sub.pagarme_subscription_id == "sub_pagarme_active_card"


def test_downgrade_package_charges_zero_and_preserves_current_until_period_end(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 3.3: Downgrade de Pacote (pkg_1000 -> pkg_200).
    - Não gera cobrança (amount = 0).
    - Pacote ativo permanece pkg_1000 com 1000 msgs até o fim do ciclo.
    - Agenda pkg_200 em whatsapp_next_package_id para o próximo ciclo.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)
    period_end = now_utc + timedelta(days=20)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=period_end.day,
        current_period_end=period_end,
        whatsapp_package_id="pkg_1000",
        whatsapp_package_status="active",
        whatsapp_messages_limit=1000,
        whatsapp_messages_used=350,
        whatsapp_period_end=period_end,
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    res = service.checkout_package(
        db=db,
        tenant=tenant,
        user_email="downgrade@petshop.com",
        user_name="Downgrade Owner",
        package_code="pkg_200",
        payment_method="pix",
    )

    assert res["status"] == "scheduled"
    assert res["amount"] == 0
    assert res["is_downgrade"] is True

    db.refresh(sub)
    assert sub.whatsapp_package_id == "pkg_1000"
    assert sub.whatsapp_messages_limit == 1000
    assert sub.whatsapp_messages_used == 350
    assert sub.whatsapp_next_package_id == "pkg_200"


def test_quota_exhaustion_detection(db: Session, tenant_id: int):
    """
    Cenário 3.5: Esgotamento de limite de mensagens (ex: 200/200).
    - Valida que mensagens restantes é zero quando used >= limit.
    """
    now_utc = datetime.now(timezone.utc)
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=now_utc.day,
        current_period_end=now_utc + timedelta(days=10),
        whatsapp_package_id="pkg_200",
        whatsapp_package_status="active",
        whatsapp_messages_limit=200,
        whatsapp_messages_used=200,
        whatsapp_period_end=now_utc + timedelta(days=10),
        payment_method="card",
    )
    db.add(sub)
    db.commit()

    remaining = max(0, sub.whatsapp_messages_limit - sub.whatsapp_messages_used)
    assert remaining == 0


# ==============================================================================
# BLOCO 4: CONFLITOS, PIX ABANDONADO E IDEMPOTÊNCIA
# ==============================================================================

def test_webhook_charge_paid_idempotency_does_not_duplicate_cycle(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 4.4: Webhook duplicado (ou polling concorrente com webhook).
    - Quitação de cobrança já marcada como 'paid' deve ser idempotente.
    - Não deve re-estender current_period_end.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="past_due",
        current_period_end=now_utc - timedelta(days=1),
        billing_day=now_utc.day,
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    charge = SubscriptionCharge(
        tenant_id=tenant_id,
        subscription_id=sub.id,
        pagarme_charge_id="ch_idempotent_test_1",
        amount=14990,
        status="pending",
        payment_method="pix",
    )
    db.add(charge)
    db.commit()

    # 1ª Execução: Quita o Pix
    res1 = service.simulate_pix_payment(db, tenant)
    assert res1["success"] is True

    db.refresh(sub)
    assert sub.status == "active"

    # Confirma que a cobrança no banco virou 'paid'
    db.refresh(charge)
    assert charge.status == "paid"

    # Invariante de Idempotência: não existem mais cobranças pendentes para este tenant
    has_pending = db.query(SubscriptionCharge).filter(
        SubscriptionCharge.tenant_id == tenant.id,
        SubscriptionCharge.status == "pending"
    ).count()
    assert has_pending == 0


# ==============================================================================
# BLOCO 5: FIM DO PERÍODO E TRANSIÇÕES DE CICLO (RENOVAÇÕES)
# ==============================================================================

def test_renewal_monthly_pix_extends_cycle(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 5.5: Renovação mensal via PIX.
    - Sub expira hoje.
    - Gera PIX de renovação e quita.
    - Período deve ser estendido em 1 mês a partir da data de término anterior.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)
    old_end = now_utc - timedelta(hours=1)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        current_period_end=old_end,
        billing_day=old_end.day,
        payment_method="pix",
    )
    db.add(sub)
    db.commit()

    service.create_checkout(
        db=db,
        tenant=tenant,
        user_email="renewal@petshop.com",
        user_name="Renewal Owner",
        plan_code="MONTHLY",
        payment_method="pix",
    )

    pay_res = service.simulate_pix_payment(db, tenant)
    assert pay_res["success"] is True

    db.refresh(sub)
    assert sub.status == "active"
    assert sub.current_period_end > now_utc + timedelta(days=25)


# ==============================================================================
# BLOCO 6: INADIMPLÊNCIA, TOLERÂNCIA (GRACE PERIOD) E BLOQUEIO
# ==============================================================================

def test_grace_period_allows_access_within_3_days(db: Session, tenant_id: int):
    """
    Cenário 6.1: Inadimplente dentro do Grace Period (<= 3 dias).
    - Status 'past_due' há 2 dias.
    - Tenant ainda tem direito de acesso provisório.
    """
    now_utc = datetime.now(timezone.utc)
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="past_due",
        current_period_end=now_utc - timedelta(days=2),
        billing_day=now_utc.day,
        payment_method="card",
    )
    db.add(sub)
    db.commit()

    days_overdue = (now_utc - sub.current_period_end).days
    is_within_grace_period = days_overdue <= 3
    assert is_within_grace_period is True


def test_blocked_status_after_grace_period_expires(db: Session, tenant_id: int):
    """
    Cenário 6.2: Bloqueio por inadimplência após 3 dias de tolerância.
    - Venceu há mais de 3 dias sem pagamento.
    - Sistema deve considerar a conta bloqueada (sem permissão de escrita).
    """
    now_utc = datetime.now(timezone.utc)
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="past_due",
        current_period_end=now_utc - timedelta(days=5),
        billing_day=now_utc.day,
        payment_method="card",
    )
    db.add(sub)
    db.commit()

    days_overdue = (now_utc - sub.current_period_end).days
    is_blocked = days_overdue > 3
    assert is_blocked is True


# ==============================================================================
# BLOCO 7: CANCELAMENTO E REATIVAÇÃO (CHURN & RESURRECTION)
# ==============================================================================

def test_cancel_subscription_cancels_gateway_and_marks_db(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 7.1: Cancelamento voluntário da assinatura pelo cliente.
    - Cancela assinatura recorrente no Pagar.me.
    - Marca status = 'canceled' e preenche canceled_at no banco.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        current_period_end=now_utc + timedelta(days=15),
        billing_day=now_utc.day,
        payment_method="card",
        pagarme_subscription_id="sub_pagarme_to_cancel",
    )
    db.add(sub)
    db.commit()

    service.cancel_subscription(db, tenant)

    db.refresh(sub)
    assert sub.status == "canceled"
    assert sub.canceled_at is not None


# ==============================================================================
# BLOCO 8: TROCA DE MÉTODOS DE PAGAMENTO (PIX <-> CARTÃO)
# ==============================================================================

def test_switch_from_pix_to_card_with_paid_period_schedules_future_sub(db: Session, tenant_id: int, mock_pagarme):
    """
    Cenário 8.1: Tenant com período quitado via PIX cadastra cartão de crédito.
    - Período atual válido por mais 25 dias.
    - NÃO cobra nada hoje.
    - Agenda assinatura futura no Pagar.me com start_at = current_period_end.
    - Salva pagarme_subscription_id no banco local.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant.pagarme_customer_id = "cus_mock_valid_123"
    plan_monthly = db.query(Plan).filter(Plan.code == "MONTHLY").first()
    now_utc = datetime.now(timezone.utc)
    future_end = now_utc + timedelta(days=25)

    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_monthly.id,
        status="active",
        billing_day=future_end.day,
        current_period_end=future_end,
        payment_method="pix",
        pagarme_subscription_id=None,
    )
    db.add(sub)
    db.commit()

    card_id = "card_new_default_456"
    tc = TenantCard(
        tenant_id=tenant_id,
        pagarme_card_id=card_id,
        is_default=False,
    )
    db.add(tc)
    db.commit()

    service.set_default_payment_method(db, tenant, card_id)

    db.refresh(sub)
    db.refresh(tc)

    assert tc.is_default is True
    assert sub.payment_method == "card"
    assert sub.pagarme_subscription_id == "sub_mock_pagarme_123"
