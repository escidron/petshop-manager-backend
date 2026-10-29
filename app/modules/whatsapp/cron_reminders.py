import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from sqlalchemy import func, not_
from sqlalchemy.orm import Session

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.subscriptions.models import Subscription
from app.modules.tenants.models import Tenant
from app.modules.whatsapp.models import WhatsAppMessage
from app.modules.whatsapp.service import WhatsAppService
from app.config.settings import settings

logger = logging.getLogger(__name__)

def send_reminder_notifications(
    db: Session,
    minutes_ahead: Optional[int] = None,
    hours_ahead: Optional[float] = None,
    tenant_id: Optional[int] = None,
    dry_run: bool = False,
    max_batch: int = 100
) -> Dict[str, Any]:
    """
    Motor escalável, concorrente e resiliente de disparo de lembretes via WhatsApp:
    1. Calcula a janela temporal (dinâmica para testes rápidos ou 24h para produção).
    2. Identifica agendamentos novos elegíveis e agendamentos com retentativas pendentes.
    3. Bloqueia individualmente cada agendamento com SKIP LOCKED prevenindo duplicatas entre réplicas Cloud Run.
    4. Valida se o agendamento ainda está ativo (não cancelado, não no passado).
    5. Dispara via Meta Cloud API com rate throttling e só debita a cota do petshop em caso de sucesso real.
    """
    if not getattr(settings, "whatsapp_enabled", True):
        logger.info("[CRON REMINDERS] Envio de lembretes desativado globalmente nas configurações.")
        return {"status": "disabled", "sent": 0, "processed": 0}

    now = datetime.now(ZoneInfo("UTC"))
    max_retries = getattr(settings, "whatsapp_max_retries", 3)

    # 1. Definição da Janela Temporal
    if minutes_ahead is not None:
        target_dt = now + timedelta(minutes=minutes_ahead)
        start_range = target_dt - timedelta(minutes=10)
        end_range = target_dt + timedelta(minutes=10)
        mode = f"minutes_ahead={minutes_ahead}"
    elif hours_ahead is not None:
        target_dt = now + timedelta(hours=hours_ahead)
        start_range = target_dt - timedelta(hours=2)
        end_range = target_dt + timedelta(hours=2)
        mode = f"hours_ahead={hours_ahead}"
    else:
        default_hours = getattr(settings, "whatsapp_reminder_hours_ahead", 24.0)
        target_dt = now + timedelta(hours=default_hours)
        start_range = target_dt - timedelta(hours=4)
        end_range = target_dt + timedelta(hours=4)
        mode = f"default_hours_ahead={default_hours}"

    logger.info(
        f"[CRON REMINDERS] Iniciando execução ({mode}) para intervalo: "
        f"{start_range.isoformat()} até {end_range.isoformat()}"
    )

    # 2. Subquery de deduplicação para novos disparos:
    # Ignora agendamentos que já possuem mensagem outbound de lembrete (enviada, em envio ou que já esgotou retentativas)
    already_tracked_subquery = (
        db.query(WhatsAppMessage.appointment_id)
        .filter(
            WhatsAppMessage.appointment_id.isnot(None),
            WhatsAppMessage.direction == "outbound",
            WhatsAppMessage.trigger_type == "reminder_24h",
            WhatsAppMessage.appointment_id == Appointment.id,
            (
                (WhatsAppMessage.status.in_(["sending", "sent", "delivered", "read"])) |
                (WhatsAppMessage.retry_count >= max_retries)
            )
        )
        .correlate(Appointment)
        .exists()
    )

    # 3. Busca de Novos Candidatos Elegíveis
    new_candidates_query = (
        db.query(Appointment.id)
        .join(Subscription, Subscription.tenant_id == Appointment.tenant_id)
        .join(Tenant, Tenant.id == Appointment.tenant_id)
        .filter(
            Tenant.is_active == True,
            Subscription.whatsapp_package_status == "active",
            (Subscription.whatsapp_messages_limit == 0) | (Subscription.whatsapp_messages_used < Subscription.whatsapp_messages_limit),
            (Subscription.whatsapp_period_end.is_(None)) | (Subscription.whatsapp_period_end > now),
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            Appointment.scheduled_at >= start_range,
            Appointment.scheduled_at <= end_range,
            # Edge case: Não enviar lembrete se o agendamento já passou ou inicia em menos de 5 min
            Appointment.scheduled_at > now + timedelta(minutes=5),
            not_(already_tracked_subquery)
        )
    )

    if tenant_id:
        new_candidates_query = new_candidates_query.filter(Appointment.tenant_id == tenant_id)

    new_appointment_ids: List[int] = [
        row[0] for row in new_candidates_query.order_by(Appointment.scheduled_at.asc()).limit(max_batch).all()
    ]

    # 4. Busca de Retentativas Pendentes (Falhas temporárias com backoff vencido)
    remaining_quota = max_batch - len(new_appointment_ids)
    retry_appointment_ids: List[int] = []
    if remaining_quota > 0 and minutes_ahead is None:
        retries_query = (
            db.query(WhatsAppMessage.appointment_id)
            .join(Appointment, Appointment.id == WhatsAppMessage.appointment_id)
            .join(Subscription, Subscription.tenant_id == WhatsAppMessage.tenant_id)
            .join(Tenant, Tenant.id == WhatsAppMessage.tenant_id)
            .filter(
                WhatsAppMessage.direction == "outbound",
                WhatsAppMessage.trigger_type == "reminder_24h",
                WhatsAppMessage.status == "failed",
                WhatsAppMessage.retry_count < max_retries,
                WhatsAppMessage.next_retry_at.isnot(None),
                WhatsAppMessage.next_retry_at <= now,
                Tenant.is_active == True,
                Subscription.whatsapp_package_status == "active",
                (Subscription.whatsapp_messages_limit == 0) | (Subscription.whatsapp_messages_used < Subscription.whatsapp_messages_limit),
                (Subscription.whatsapp_period_end.is_(None)) | (Subscription.whatsapp_period_end > now),
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                # Edge case: Só retenta se o agendamento ainda está a pelo menos 30 min no futuro
                Appointment.scheduled_at > now + timedelta(minutes=30)
            )
        )
        if tenant_id:
            retries_query = retries_query.filter(WhatsAppMessage.tenant_id == tenant_id)

        retry_appointment_ids = [row[0] for row in retries_query.limit(remaining_quota).all()]

    total_candidates = len(new_appointment_ids) + len(retry_appointment_ids)
    logger.info(
        f"[CRON REMINDERS] Agendamentos identificados: {len(new_appointment_ids)} novos, "
        f"{len(retry_appointment_ids)} retentativas pendentes (Total: {total_candidates})"
    )

    if dry_run:
        return {
            "status": "dry_run",
            "eligible_new_count": len(new_appointment_ids),
            "eligible_retry_count": len(retry_appointment_ids),
            "new_appointment_ids": new_appointment_ids,
            "retry_appointment_ids": retry_appointment_ids,
            "window": {
                "start": start_range.isoformat(),
                "end": end_range.isoformat()
            }
        }

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    service = WhatsAppService()

    # Processamento Concorrente com Lock Linha-a-Linha (SKIP LOCKED)
    candidate_items = [
        (appt_id, False) for appt_id in new_appointment_ids
    ] + [
        (appt_id, True) for appt_id in retry_appointment_ids
    ]

    for appt_id, is_retry in candidate_items:
        try:
            # Trava pontual e isolada por agendamento: se outra réplica estiver processando, pula imediatamente
            locked_appt = (
                db.query(Appointment)
                .filter(Appointment.id == appt_id)
                .with_for_update(skip_locked=True)
                .first()
            )

            if not locked_appt:
                skipped_count += 1
                logger.debug(f"[CRON REMINDERS] Agendamento #{appt_id} bloqueado por outro worker ou não encontrado. Pulando.")
                continue

            success, message = service.send_whatsapp_notification(
                db=db,
                tenant_id=locked_appt.tenant_id,
                appointment_id=locked_appt.id,
                trigger_type="reminder_24h",
                is_retry=is_retry
            )

            if success:
                sent_count += 1
                logger.info(f"[CRON REMINDERS] Lembrete disparado para Agendamento #{locked_appt.id} (Tenant #{locked_appt.tenant_id})")
            else:
                failed_count += 1
                logger.warning(f"[CRON REMINDERS] Falha ao disparar lembrete #{locked_appt.id}: {message}")

            # Throttling adaptativo: pausa de 50ms para respeitar limites de vazão da Meta API em lote
            time.sleep(0.05)

        except Exception as e:
            failed_count += 1
            db.rollback()
            logger.error(f"[CRON REMINDERS] Erro inesperado ao processar agendamento #{appt_id}: {str(e)}", exc_info=True)

    summary = {
        "status": "completed",
        "processed": total_candidates,
        "sent": sent_count,
        "failed": failed_count,
        "skipped_concurrent": skipped_count,
        "mode": mode,
        "window": {
            "start": start_range.isoformat(),
            "end": end_range.isoformat()
        }
    }
    logger.info(f"[CRON REMINDERS] Execução finalizada: {summary}")
    return summary
