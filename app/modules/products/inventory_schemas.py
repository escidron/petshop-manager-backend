from pydantic import BaseModel, Field, AliasChoices
from datetime import datetime
from typing import Optional

class InventoryLogResponse(BaseModel):
    id: int
    product_id: int
    quantity_changed: int = Field(validation_alias=AliasChoices("quantity_changed", "quantity_change"))
    log_type: str = Field(validation_alias=AliasChoices("log_type", "change_type"))
    description: Optional[str] = Field(validation_alias=AliasChoices("description", "notes"))
    created_at: datetime
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

class GlobalInventoryLogResponse(InventoryLogResponse):
    product_name: str
    product_sku: Optional[str] = None

class StockAdjustmentRequest(BaseModel):
    quantity_change: int
    change_type: str = "manual_adjustment"
    notes: Optional[str] = None
