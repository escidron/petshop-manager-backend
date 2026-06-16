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
    created_at: datetime

    class Config:
        from_attributes = True
