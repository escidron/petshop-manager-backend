import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.config.settings import settings
from app.services.email.service import EmailService
from app.modules.auth.token import decode_token

logger = logging.getLogger("api.observability")

router = APIRouter(prefix="/observability", tags=["observability"])

class ClientErrorPayload(BaseModel):
    message: str
    stack: Optional[str] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None

@router.post("/client-error")
async def report_client_error(payload: ClientErrorPayload, request: Request):
    user_id = payload.user_id
    tenant_id = payload.tenant_id

    # Try to extract from request cookies if not provided
    if not user_id or not tenant_id:
        token = request.cookies.get("access_token")
        if token:
            try:
                decoded = decode_token(token)
                if decoded:
                    if not user_id:
                        user_id = str(decoded.get("user_id", "N/A"))
                    if not tenant_id:
                        tenant_id = str(decoded.get("tenant_id", "N/A"))
            except Exception:
                pass

    # Fallback to defaults
    user_id = user_id or "N/A"
    tenant_id = tenant_id or "N/A"

    # 1. Log the error in the server console/logs
    logger.error(
        f"[CLIENT_ERROR] Message: {payload.message}\n"
        f"URL: {payload.url}\n"
        f"User ID: {user_id} | Tenant ID: {tenant_id}\n"
        f"User Agent: {payload.user_agent}\n"
        f"Stack Trace:\n{payload.stack}"
    )

    # 2. If email service is configured (Resend) and environment is production, send email notification
    if settings.RESEND_KEY and settings.ENVIRONMENT == "production":
        try:
            email_service = EmailService()
            recipient = settings.ADMIN_EMAIL or settings.DEFAULT_FROM_EMAIL
            subject = f"🚨 ERRO CLIENTE - {settings.APP_NAME}"
            html_content = f"""
            <html>
                <body style="font-family: sans-serif; line-height: 1.5; color: #333;">
                    <h2 style="color: #dc2626; border-bottom: 2px solid #dc2626; padding-bottom: 8px;">Erro de Interface Capturado (MVP)</h2>
                    <p><strong>Mensagem:</strong> {payload.message}</p>
                    <p><strong>Página/URL:</strong> {payload.url}</p>
                    <p><strong>Usuário ID:</strong> {user_id} | <strong>Tenant ID:</strong> {tenant_id}</p>
                    <p><strong>Navegador:</strong> {payload.user_agent}</p>
                    <h3>Pilha de Execução (Stack Trace):</h3>
                    <pre style="background: #1e1e1e; color: #f87171; padding: 15px; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 13px;">
{payload.stack or 'Sem stack trace disponível'}
                    </pre>
                </body>
            </html>
            """
            email_service.provider.send_email(
                to=recipient,
                subject=subject,
                html=html_content,
                text=f"Erro no front-end: {payload.message} na URL {payload.url}."
            )
        except Exception as e:
            logger.error(f"Failed to send telemetry email: {str(e)}")

    return {"status": "ok", "message": "Telemetry received"}
