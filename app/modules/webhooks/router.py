from fastapi import APIRouter, Header, Request

from app.modules.subscriptions.service import handle_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/pagarme")
async def pagarme_webhook(
    request: Request,
    x_hub_signature: str = Header(default="", alias="x-hub-signature"),
):
    """
    Recebe eventos do Pagar.me. Usa o corpo raw (bytes) para validar a assinatura HMAC.
    IMPORTANTE: Este endpoint NÃO deve ter middleware que consuma o body antes.
    """
    payload = await request.body()
    handle_webhook_event(payload, x_hub_signature)
    return {"status": "ok"}
