import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.settings import settings
from app.modules.auth.token import decode_token
from app.modules.users.models import User
from app.modules.whatsapp.models import WhatsAppMessage
from app.modules.whatsapp.schemas import SimulateInboundRequest, WhatsAppMessageResponse
from app.modules.whatsapp.service import WhatsAppService
from app.modules.whatsapp.cron_reminders import send_reminder_notifications

logger = logging.getLogger(__name__)

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
        return PlainTextResponse(content=str(hub_challenge))
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch"
    )

def check_cron_access(request: Request, db: Session = Depends(get_db)):
    """
    Permite acesso se:
    1. Ambiente for 'development' (testes locais rápidos).
    2. Header 'X-Cron-Secret' coincidir com settings.whatsapp_cron_secret (Google Cloud Scheduler).
    3. Usuário autenticado for 'admin'.
    """
    if settings.ENVIRONMENT == "development":
        return True

    cron_header = request.headers.get("X-Cron-Secret")
    if cron_header and getattr(settings, "whatsapp_cron_secret", None) and cron_header == settings.whatsapp_cron_secret:
        return True

    token = request.cookies.get("access_token")
    if token:
        payload = decode_token(token)
        if payload:
            user = db.query(User).filter(User.id == int(payload["user_id"])).first()
            if user and user.role == "admin":
                return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acesso não autorizado para acionamento do agendador (cron)"
    )


@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Recebe eventos em tempo real do WhatsApp Meta Cloud API (produção):
    1. Mensagens de entrada e cliques nos botões Confirmar/Cancelar.
    2. Recibos de entrega e leitura (sent, delivered, read, failed).
    """
    payload = await request.json()
    service = WhatsAppService()
    
    try:
        entries = payload.get("entry", [])
        if not entries:
            return {"status": "ignored"}

        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # 1. Tratamento de Recibos de Status (delivered, read, failed)
                statuses = value.get("statuses", [])
                for st in statuses:
                    wamid = st.get("id")
                    meta_status = st.get("status")  # delivered, read, failed
                    errors = st.get("errors", [])
                    if wamid and meta_status:
                        db_msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.meta_message_id == wamid).first()
                        if db_msg:
                            db_msg.status = meta_status
                            if meta_status == "failed":
                                if errors:
                                    err = errors[0]
                                    db_msg.error_code = str(err.get("code", "UNKNOWN"))
                                    err_title = err.get("title", "")
                                    err_detail = err.get("message", "")
                                    db_msg.error_message = f"Meta delivery failed: {err_title} - {err_detail}"[:2000]

                                # REEMBOLSO JUSTO: se a entrega falhar na ponta e ainda não tiver sido reembolsada, estorna a cota
                                if not db_msg.refunded and db_msg.tenant_id:
                                    service.refund_tenant_message_quota(db, db_msg.tenant_id)
                                    db_msg.refunded = True
                                    logger.info(f"[WHATSAPP WEBHOOK] Cota estornada para Tenant #{db_msg.tenant_id} (wamid: {wamid})")
                            db.commit()

                # 2. Tratamento de Mensagens Recebidas e Botões
                messages = value.get("messages", [])
                for message in messages:
                    from_number = message.get("from")
                    msg_type = message.get("type")
                    text = ""
                    button_payload = None

                    # A. Botão de Template Oficial Meta (Quick Reply)
                    if msg_type == "button":
                        btn = message.get("button", {})
                        button_payload = btn.get("payload")
                        text = btn.get("text", "")

                    # B. Mensagens Interativas (button_reply ou list_reply)
                    elif msg_type == "interactive":
                        interactive = message.get("interactive", {})
                        reply_type = interactive.get("type")
                        if reply_type == "button_reply":
                            button_reply = interactive.get("button_reply", {})
                            button_payload = button_reply.get("id")
                            text = button_reply.get("title", "")
                        elif reply_type == "list_reply":
                            list_reply = interactive.get("list_reply", {})
                            button_payload = list_reply.get("id")
                            text = list_reply.get("title", "")

                    # C. Mensagem de Texto Livre
                    elif msg_type == "text":
                        text = message.get("text", {}).get("body", "")

                    logger.info(
                        f"[WHATSAPP WEBHOOK] Mensagem recebida de {from_number} "
                        f"(tipo: '{msg_type}', text: '{text}', payload: '{button_payload}')"
                    )

                    if from_number and (text or button_payload):
                        service.process_incoming_message(
                            db=db,
                            from_number=from_number,
                            text=text,
                            button_payload=button_payload
                        )

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Erro ao processar webhook real do WhatsApp: {str(e)}", exc_info=True)
        return {"status": "ignored"}


@router.post("/cron/send-reminders")
def trigger_cron_reminders(
    minutes_ahead: Optional[int] = None,
    hours_ahead: Optional[float] = None,
    tenant_id: Optional[int] = None,
    dry_run: bool = False,
    max_batch: int = 100,
    db: Session = Depends(get_db),
    _ = Depends(check_cron_access)
):
    """
    Endpoint com proteção de concorrência (SKIP LOCKED) para envio de lembretes.
    Suporta parâmetros opcionais para homologação e testes locais imediatos:
    - `minutes_ahead`: Teste com agendamentos daqui a N minutos (ex: 15).
    - `hours_ahead`: Antecedência customizada em horas (default: 24h).
    - `tenant_id`: Restringe a execução apenas ao tenant de teste informado.
    - `dry_run`: Apenas audita os agendamentos elegíveis sem disparar ou debitar cotas.
    """
    result = send_reminder_notifications(
        db=db,
        minutes_ahead=minutes_ahead,
        hours_ahead=hours_ahead,
        tenant_id=tenant_id,
        dry_run=dry_run,
        max_batch=max_batch
    )
    return result
