import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from app.modules.whatsapp.service import WhatsAppService, MetaResponseError
from app.modules.whatsapp.models import WhatsAppMessage
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.subscriptions.models import Subscription
from app.modules.tenants.models import Tenant
from app.modules.clients.models import Client
from app.config.settings import settings

def test_validate_whatsapp_phone():
    service = WhatsAppService()

    # Telefone fixo (8 dígitos após DDD iniciando em 2..5) deve ser rejeitado
    is_valid, phone, reason = service.validate_whatsapp_phone("1132345678")
    assert not is_valid
    assert "Telefone fixo" in reason

    # Telefone celular (11 dígitos com 9) deve ser aceito e normalizado
    is_valid, phone, reason = service.validate_whatsapp_phone("(11) 98765-4321")
    assert is_valid
    assert phone == "5511987654321"

    # Celular com DDI 55
    is_valid, phone, reason = service.validate_whatsapp_phone("+55 11 98765-4321")
    assert is_valid
    assert phone == "5511987654321"

    # Telefone sem nono dígito (número celular antigo)
    is_valid, phone, reason = service.validate_whatsapp_phone("1187654321")
    assert is_valid
    assert phone == "5511987654321"


def test_atomic_quota_debit_and_zero_debit_on_failure(db, tenant_id):
    service = WhatsAppService()

    # Garante pacote de WhatsApp ativo na assinatura do tenant de teste
    sub = db.query(Subscription).filter_by(tenant_id=tenant_id).first()
    if not sub:
        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=1,
            status="active",
            current_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30),
            whatsapp_package_id="pkg_100",
            whatsapp_package_status="active",
            whatsapp_messages_limit=10,
            whatsapp_messages_used=0,
            whatsapp_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
        )
        db.add(sub)
    else:
        sub.whatsapp_package_id = "pkg_100"
        sub.whatsapp_package_status = "active"
        sub.whatsapp_messages_limit = 10
        sub.whatsapp_messages_used = 0
        sub.whatsapp_period_end = datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
    db.commit()

    client = Client(tenant_id=tenant_id, name="Cliente Teste", phone="11999998888")
    db.add(client)
    db.flush()

    appt = Appointment(
        tenant_id=tenant_id,
        client_id=client.id,
        status=AppointmentStatus.CONFIRMED,
        scheduled_at=datetime.now(ZoneInfo("UTC")) + timedelta(hours=24)
    )
    db.add(appt)
    db.commit()

    # 1. Simula falha na Meta API (ex: erro 132001 template inexistente)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {
            "code": 132001,
            "message": "Template does not exist",
            "type": "OAuthException"
        }
    }
    mock_resp.text = '{"error": {"code": 132001}}'

    with patch.object(service, "_send_meta_template_message", side_effect=MetaResponseError(mock_resp)):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            success, msg = service.send_whatsapp_notification(db, tenant_id, appt.id, "reminder_24h")
            assert not success
            assert "132001" in msg

    # Valida que o saldo NÃO foi debitado!
    db.refresh(sub)
    assert sub.whatsapp_messages_used == 0

    # Valida que foi registrado como failed com erro
    record = db.query(WhatsAppMessage).filter_by(appointment_id=appt.id).first()
    assert record is not None
    assert record.status == "failed"
    assert record.error_code == "132001"
    assert record.retry_count == settings.whatsapp_max_retries  # Erro permanente não deve retentar

    # 2. Agora simula sucesso
    with patch.object(service, "_send_meta_template_message", return_value=("wamid_test_123", {})):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            success, msg = service.send_whatsapp_notification(db, tenant_id, appt.id, "reminder_24h", is_retry=True)
            assert success

    # Valida que o saldo FOI debitado exatamente em 1
    db.refresh(sub)
    assert sub.whatsapp_messages_used == 1

    # Valida atualização do registro existente (sem duplicar)
    records = db.query(WhatsAppMessage).filter_by(appointment_id=appt.id).all()
    assert len(records) == 1
    assert records[0].status == "sent"
    assert records[0].meta_message_id == "wamid_test_123"


def test_deduplication_prevents_duplicate_sending(db, tenant_id):
    service = WhatsAppService()

    sub = db.query(Subscription).filter_by(tenant_id=tenant_id).first()
    if not sub:
        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=1,
            status="active",
            current_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30),
            whatsapp_package_id="pkg_100",
            whatsapp_package_status="active",
            whatsapp_messages_limit=10,
            whatsapp_messages_used=0,
            whatsapp_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
        )
        db.add(sub)
    else:
        sub.whatsapp_package_id = "pkg_100"
        sub.whatsapp_package_status = "active"
        sub.whatsapp_messages_limit = 10
        sub.whatsapp_messages_used = 0
        sub.whatsapp_period_end = datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
    db.commit()

    client = Client(tenant_id=tenant_id, name="Cliente Dedup", phone="11999997777")
    db.add(client)
    db.flush()

    appt = Appointment(
        tenant_id=tenant_id,
        client_id=client.id,
        status=AppointmentStatus.CONFIRMED,
        scheduled_at=datetime.now(ZoneInfo("UTC")) + timedelta(hours=24)
    )
    db.add(appt)
    db.commit()

    with patch.object(service, "_send_meta_template_message", return_value=("wamid_first", {})):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            # Primeiro envio: deve ter sucesso
            s1, m1 = service.send_whatsapp_notification(db, tenant_id, appt.id, "reminder_24h")
            assert s1

            # Segundo envio imediato: deve ser bloqueado pela camada de deduplicação
            s2, m2 = service.send_whatsapp_notification(db, tenant_id, appt.id, "reminder_24h")
            assert not s2
            assert "já enviada" in m2

    # Verifica que apenas 1 registro e 1 cota foi consumida
    db.refresh(sub)
    assert sub.whatsapp_messages_used == 1

    count = db.query(WhatsAppMessage).filter_by(appointment_id=appt.id, trigger_type="reminder_24h").count()
    assert count == 1


def test_webhook_failure_refunds_quota(db, tenant_id):
    service = WhatsAppService()

    sub = db.query(Subscription).filter_by(tenant_id=tenant_id).first()
    if not sub:
        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=1,
            status="active",
            current_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30),
            whatsapp_package_id="pkg_100",
            whatsapp_package_status="active",
            whatsapp_messages_limit=10,
            whatsapp_messages_used=1,
            whatsapp_period_end=datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
        )
        db.add(sub)
    else:
        sub.whatsapp_package_id = "pkg_100"
        sub.whatsapp_package_status = "active"
        sub.whatsapp_messages_limit = 10
        sub.whatsapp_messages_used = 1  # 1 já debitada
        sub.whatsapp_period_end = datetime.now(ZoneInfo("UTC")) + timedelta(days=30)
    db.commit()

    msg = WhatsAppMessage(
        tenant_id=tenant_id,
        phone_number="5511999996666",
        direction="outbound",
        trigger_type="reminder_24h",
        content="Mensagem de teste",
        status="sent",
        meta_message_id="wamid_refund_test",
        refunded=False
    )
    db.add(msg)
    db.commit()

    # Simula webhook de falha na entrega
    # Refund 1: Deve estornar a cota
    refunded = service.refund_tenant_message_quota(db, tenant_id)
    assert refunded
    msg.status = "failed"
    msg.refunded = True
    db.commit()

    db.refresh(sub)
    assert sub.whatsapp_messages_used == 0

    # Segundo webhook duplicado para o mesmo wamid: msg.refunded já é True, não estorna novamente
    assert msg.refunded is True


def test_incoming_message_confirms_silently_without_outbound_reply(db, tenant_id):
    service = WhatsAppService()

    client = Client(tenant_id=tenant_id, name="Cliente Resposta", phone="11988887777")
    db.add(client)
    db.flush()

    appt = Appointment(
        tenant_id=tenant_id,
        client_id=client.id,
        scheduled_at=datetime.now(ZoneInfo("UTC")) + timedelta(hours=20),
        status=AppointmentStatus.PENDING
    )
    db.add(appt)
    db.commit()

    # Por padrão (whatsapp_auto_reply_enabled=False), não envia mensagem de volta
    with patch.object(settings, "whatsapp_auto_reply_enabled", False):
        with patch.object(service, "_send_meta_text_message") as mock_meta_text:
            result = service.process_incoming_message(
                db=db,
                from_number="5511988887777",
                text="Sim, confirmado!"
            )
            # Verifica que o agendamento foi confirmado
            db.refresh(appt)
            assert appt.status == AppointmentStatus.CONFIRMED

            # Verifica que NENHUMA chamada para a Meta API foi feita
            mock_meta_text.assert_not_called()

            # Verifica que a mensagem retornada é a inbound gravada
            assert result.direction == "inbound"
            assert result.status == "received"
            assert result.appointment_id == appt.id
            assert result.tenant_id == tenant_id

            # Garante que nenhuma mensagem outbound de resposta foi criada no banco
            outbound_replies = db.query(WhatsAppMessage).filter(
                WhatsAppMessage.appointment_id == appt.id,
                WhatsAppMessage.direction == "outbound"
            ).all()
            assert len(outbound_replies) == 0


def test_staging_safeguard_blocks_real_clients(db, tenant_id):
    service = WhatsAppService()

    # Em staging, mesmo que alguém desative whatsapp_sandbox_mode, clientes reais nunca recebem mensagem!
    with patch.object(settings, "ENVIRONMENT", "staging"):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            with patch.object(settings, "whatsapp_sandbox_number", "5511988887777"):
                # Cliente real (número qualquer diferente do sandbox) deve ser bloqueado
                assert service._is_sandbox_target("5511999991234") is True
                assert service._is_sandbox_target("(11) 97777-6666") is True

                # Apenas o telefone de teste configurado é liberado para disparos
                assert service._is_sandbox_target("5511988887777") is False
                assert service._is_sandbox_target("(11) 98888-7777") is False

    # Em staging sem número de teste configurado: bloqueia TUDO
    with patch.object(settings, "ENVIRONMENT", "staging"):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            with patch.object(settings, "whatsapp_sandbox_number", ""):
                assert service._is_sandbox_target("5511988887777") is True
                assert service._is_sandbox_target("5511999991234") is True

    # Em produção: libera envio normal
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "whatsapp_sandbox_mode", False):
            assert service._is_sandbox_target("5511999991234") is False


