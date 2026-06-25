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
    pet_id: int | None = None
    employee_id: int | None = None
    client_package_id_to_pay: int | None = None

class SaleItemResponse(SaleItemBase):
    id: int
    sale_id: int
    employee_id: int | None = None

    class Config:
        from_attributes = True

# Nested helpers
class ClientBrief(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class ServiceBrief(BaseModel):
    id: int
    price_cents: int

    class Config:
        from_attributes = True

class AppointmentItemBrief(BaseModel):
    services: list[ServiceBrief] = []

    class Config:
        from_attributes = True

class AppointmentBrief(BaseModel):
    id: int
    client: ClientBrief
    items: list[AppointmentItemBrief] = []

    class Config:
        from_attributes = True

# Sales
class SaleBase(BaseModel):
    client_id: int | None = None
    pet_id: int | None = None
    appointment_id: int | None = None
    total_amount: float = Field(ge=0)
    discount_amount: float = Field(default=0.0, ge=0)
    payment_method: Literal["pix", "credit_card", "debit_card", "money", "other", "package"]
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
    client: ClientBrief | None = None
    appointment: AppointmentBrief | None = None

    class Config:
        from_attributes = True
