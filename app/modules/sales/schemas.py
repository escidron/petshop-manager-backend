from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

# Sale Items

class SaleItemBase(BaseModel):
    item_type: Literal["product", "service", "package"]
    item_id: int
    name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    subtotal: float = Field(ge=0)

class SaleItemCreate(SaleItemBase):
    pet_id: int | None = None  # Para pacotes: gera ClientPackage automaticamente na venda
    employee_id: int | None = None  # Funcionário responsável pelo item (gera comissão)

class SaleItemResponse(SaleItemBase):
    id: int
    sale_id: int
    employee_id: int | None = None

    class Config:
        from_attributes = True

# Sales
class SaleBase(BaseModel):
    client_id: int | None = None
    pet_id: int | None = None
    appointment_id: int | None = None
    total_amount: float = Field(ge=0)
    payment_method: Literal["pix", "credit_card", "debit_card", "money", "other"]
    status: Literal["completed", "canceled"] = "completed"

class SaleCreate(SaleBase):
    items: list[SaleItemCreate]

class SaleUpdateStatus(BaseModel):
    status: Literal["canceled"]

class SaleResponse(SaleBase):
    id: int
    tenant_id: int
    created_at: datetime
    items: list[SaleItemResponse] = []

    class Config:
        from_attributes = True
