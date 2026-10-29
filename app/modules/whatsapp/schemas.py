from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class SimulateInboundRequest(BaseModel):
    phone_number: str
    content: str
    button_payload: Optional[str] = None

class WhatsAppMessageResponse(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    appointment_id: Optional[int] = None
    phone_number: str
    direction: str
    content: str
    buttons: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "sent"
    trigger_type: Optional[str] = None
    meta_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None
    refunded: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
