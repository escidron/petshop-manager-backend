from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PlanResponse(BaseModel):
    id: int
    code: str
    name: str
    price_cents: int
    currency: str
    billing_cycle: str
    trial_days: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
