from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class InventoryLogResponse(BaseModel):
    id: int
    product_id: int
    quantity_change: int
    change_type: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class StockAdjustmentRequest(BaseModel):
    quantity_change: int
    change_type: str = "manual_adjustment"
    notes: Optional[str] = None
