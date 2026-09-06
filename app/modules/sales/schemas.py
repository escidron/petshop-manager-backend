from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Any

from app.modules.clients.schemas import ClientResponse
from app.modules.tenant_services.schemas import ServiceResponse
from app.modules.products.schemas import ProductResponse
from app.modules.packages.schemas import Package
from app.modules.appointments.schemas import AppointmentResponse
from app.modules.client_packages.schemas import ClientPackageResponse
from app.modules.pets.schemas import PetResponse

# Sale Items

class SaleItemBase(BaseModel):
    item_type: Literal["product", "service", "package"]
    item_id: int
    name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    subtotal: float = Field(ge=0)

class SaleItemCreate(SaleItemBase):
    pet_ids: list[int] | None = None
    employee_id: int | None = None
    client_package_id_to_pay: int | None = None
    appointment_id: int | None = None

class SaleItemResponse(SaleItemBase):
    id: int
    sale_id: int
    employee_id: int | None = None
    appointment_id: int | None = None

    class Config:
        from_attributes = True

# Nested helpers
class PetBrief(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class ClientBrief(BaseModel):
    id: int
    name: str
    pets: list[PetBrief] = []

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

# Comanda Items
class ComandaItemBase(BaseModel):
    item_type: Literal["product", "service", "package"]
    item_id: int
    name: str
    quantity: int = Field(gt=0, default=1)
    unit_price: float = Field(ge=0, default=0.0)
    subtotal: float = Field(ge=0, default=0.0)
    employee_id: int | None = None
    pet_ids: list[int] | None = None
    client_package_id_to_pay: int | None = None
    unit: str | None = "UN"
    appointment_id: int | None = None

class ComandaItemCreate(ComandaItemBase):
    pass

class ComandaItemResponse(ComandaItemBase):
    id: int
    comanda_id: int

    class Config:
        from_attributes = True

# Comandas
class ComandaSaveRequest(BaseModel):
    comanda_id: int | None = None
    client_id: int
    appointment_id: int | None = None
    items: list[ComandaItemCreate] = []
    discount_amount: float = Field(default=0.0, ge=0)
    notes: str | None = None

class ComandaResponse(BaseModel):
    id: int
    tenant_id: int
    client_id: int
    appointment_id: int | None = None
    status: Literal["open", "completed", "canceled"] = "open"
    total_amount: float = Field(ge=0)
    discount_amount: float = Field(default=0.0, ge=0)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ComandaItemResponse] = []
    client: ClientBrief | None = None

    class Config:
        from_attributes = True

class PaginatedComandasResponse(BaseModel):
    items: list[ComandaResponse]
    total: int

# Sale Payments
class SalePaymentBase(BaseModel):
    payment_method: Literal["pix", "credit_card", "debit_card", "money", "other", "package"]
    amount: float = Field(ge=0)

class SalePaymentCreate(SalePaymentBase):
    pass

class SalePaymentResponse(SalePaymentBase):
    id: int
    sale_id: int

    class Config:
        from_attributes = True


# Sales
class SaleBase(BaseModel):
    client_id: int | None = None
    pet_id: int | None = None
    appointment_id: int | None = None
    comanda_id: int | None = None
    total_amount: float = Field(ge=0)
    discount_amount: float = Field(default=0.0, ge=0)
    payment_method: Literal["pix", "credit_card", "debit_card", "money", "other", "package", "multiple"]
    status: Literal["completed", "canceled"] = "completed"

class SaleCreate(SaleBase):
    items: list[SaleItemCreate]
    payments: list[SalePaymentCreate] | None = None
    cash_register_id: int | None = None
    unpaid_remainder: float | None = None

class SaleUpdateStatus(BaseModel):
    status: Literal["canceled"]

class SaleResponse(SaleBase):
    id: int
    tenant_id: int
    created_at: datetime
    items: list[SaleItemResponse] = []
    payments: list[SalePaymentResponse] = []
    client: ClientBrief | None = None
    appointment: AppointmentBrief | None = None

    class Config:
        from_attributes = True

# POS Optimization Schemas
class POSStartupResponse(BaseModel):
    products: list[ProductResponse]
    services: list[ServiceResponse]
    packages: list[Package]
    clients: list[ClientResponse]
    appointments: list[AppointmentResponse]
    pets: list[PetResponse]
    open_comandas: list[ComandaResponse] = []
    cash_registers: list[Any] = []
    cash_status: Any | None = None

class POSClientDetailsResponse(BaseModel):
    client_pets: list[PetResponse]
    client_packages: list[ClientPackageResponse]
    client_appointments: list[AppointmentResponse]
    open_comandas: list[ComandaResponse] = []
