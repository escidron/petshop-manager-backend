from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.config.database import get_db
from app.config.settings import settings
from app.modules.auth.token import decode_token
from app.modules.users.models import User
from app.modules.whatsapp.models import WhatsAppMessage
from app.modules.whatsapp.schemas import SimulateInboundRequest, WhatsAppMessageResponse
from app.modules.whatsapp.service import WhatsAppService
from app.modules.whatsapp.cron_reminders import send_reminder_notifications

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

def check_sandbox_access(request: Request, db: Session = Depends(get_db)):
    """
    Permite acesso irrestrito se o ambiente for 'development'.
    Caso contrário, exige que o usuário autenticado seja um 'admin'.
    """
    if settings.ENVIRONMENT == "development":
        return True

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária"
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )

    user = db.query(User).filter(User.id == int(payload["user_id"])).first()
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administradores"
        )
    return True

@router.get("/messages", response_model=List[WhatsAppMessageResponse])
def get_whatsapp_messages(
    phone_number: Optional[str] = None,
    db: Session = Depends(get_db),
    _ = Depends(check_sandbox_access)
):
    """
    Retorna o histórico de mensagens trocadas com um número de telefone específico (ou todas).
    Ordenado cronologicamente.
    """
    query = db.query(WhatsAppMessage)
    if phone_number:
        # Normaliza o telefone recebido para buscar no banco
        service = WhatsAppService()
        normalized_phone = service.normalize_phone_number(phone_number)
        
        # Filtra comparando os últimos 9 dígitos
        suffix = normalized_phone[-9:] if len(normalized_phone) >= 9 else normalized_phone
        query = query.filter(WhatsAppMessage.phone_number.like(f"%{suffix}"))
        
    return query.order_by(WhatsAppMessage.created_at.asc()).all()

@router.post("/simulate-inbound", response_model=WhatsAppMessageResponse)
def simulate_inbound_message(
    payload: SimulateInboundRequest,
    db: Session = Depends(get_db),
    _ = Depends(check_sandbox_access)
):
    """
    Simula uma resposta do cliente (inbound) e processa a regra de confirmação/cancelamento.
    Retorna a resposta automática que foi gerada pelo SaaS (outbound).
    """
    service = WhatsAppService()
    try:
        reply = service.process_incoming_message(
            db=db,
            from_number=payload.phone_number,
            text=payload.content,
            button_payload=payload.button_payload
        )
        return reply
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao simular mensagem: {str(e)}"
        )

# --- WEBHOOK OFICIAL (PRODUÇÃO) ---

@router.get("/webhook")
def verify_meta_webhook(
    request: Request,
    verify_token: str = None,
    challenge: str = None
):
    """
    Validação da URL do Webhook do WhatsApp (Meta Cloud API).
    Exige que o 'verify_token' enviado pelo Meta coincida com a nossa chave configurada.
    """
    # Ex: /api/v1/whatsapp/webhook?hub.verify_token=...&hub.challenge=...
    # FastAPI mapeia os parâmetros da query
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_webhook_verify_token:
        return int(hub_challenge)
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch"
    )

@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Recebe eventos em tempo real do WhatsApp Meta Cloud API (produção).
    """
    payload = await request.json()
    service = WhatsAppService()
    
    try:
        # A Meta envia as mensagens estruturadas dentro de entry -> changes -> value -> messages
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            message = messages[0]
            from_number = message.get("from")
            text = ""
            button_payload = None

            # Verifica se foi um clique de botão interativo
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_payload = button_reply.get("id")
                    text = button_reply.get("title")
            elif message.get("type") == "text":
                text = message.get("text", {}).get("body", "")

            if from_number and (text or button_payload):
                service.process_incoming_message(
                    db=db,
                    from_number=from_number,
                    text=text,
                    button_payload=button_payload
                )

        return {"status": "success"}
    except Exception as e:
        # Retorna 200 para o WhatsApp não parar de tentar enviar webhooks, mas registra o log de erro
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao processar webhook real do WhatsApp: {str(e)}")
        return {"status": "ignored"}

@router.post("/cron/send-reminders")
def trigger_cron_reminders(
    db: Session = Depends(get_db),
    _ = Depends(check_sandbox_access)
):
    """
    Endpoint manual ou via agendador para disparar lembretes de WhatsApp para agendamentos de amanhã.
    """
    sent = send_reminder_notifications(db)
    return {"status": "success", "reminders_sent": sent}
