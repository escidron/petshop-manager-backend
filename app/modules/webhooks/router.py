from fastapi import APIRouter, Header, Request

from app.modules.subscriptions.service import handle_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
):
    """
    Recebe eventos do Stripe. Usa o corpo raw (bytes) para validar a assinatura.
    IMPORTANTE: Este endpoint NÃO deve ter middleware que consuma o body antes.
    """
    payload = await request.body()
    handle_webhook_event(payload, stripe_signature)
    return {"status": "ok"}
