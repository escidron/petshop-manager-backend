import logging
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.whatsapp.models import WhatsAppMessage
from app.modules.whatsapp.service import WhatsAppService

logger = logging.getLogger(__name__)

def send_reminder_notifications(db: Session) -> int:
    """
    Busca agendamentos marcados para aproximadamente amanhã (entre 20 e 30 horas no futuro)
    com status 'pending' ou 'confirmed' que ainda não receberam lembrete, e dispara as mensagens.
    Retorna o número total de lembretes enviados.
    """
    now = datetime.now()
    start_range = now + timedelta(hours=20)
    end_range = now + timedelta(hours=30)

    logger.info(f"Executando cron de lembretes de WhatsApp para horários entre {start_range} e {end_range}")

    # Achar agendamentos no intervalo
    appointments = db.query(Appointment).filter(
        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
        Appointment.scheduled_at >= start_range,
        Appointment.scheduled_at <= end_range
    ).all()

    sent_count = 0
    service = WhatsAppService()

    for app in appointments:
        # Verifica se já existe mensagem de saída contendo "lembrar" ou "lembrete"
        already_sent = db.query(WhatsAppMessage).filter(
            WhatsAppMessage.appointment_id == app.id,
            WhatsAppMessage.direction == "outbound",
            WhatsAppMessage.content.like("%lembrar%")
        ).first()

        if not already_sent:
            try:
                service.send_whatsapp_notification(db, app.tenant_id, app.id, "reminder_24h")
                sent_count += 1
                logger.info(f"Lembrete enviado com sucesso para o agendamento {app.id}")
            except Exception as e:
                logger.error(f"Erro ao enviar lembrete do agendamento {app.id}: {str(e)}")

    logger.info(f"Cron finalizado. Total de lembretes enviados: {sent_count}")
    return sent_count
