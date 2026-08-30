from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal


class CashRegisterResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CashRegisterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, description="Nome do caixa/terminal")


class CashRegisterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_active: bool | None = None


class CashDestinationAccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    is_default: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CashDestinationAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, description="Nome da conta de destino/origem")
    account_type: str = Field(default="internal_cash", description="Tipo: internal_cash, bank_account, safe, other")
    is_default: bool = False


class CashDestinationAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    account_type: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class CashMovementResponse(BaseModel):
    id: int
    session_id: int
    user_id: int | None = None
    user_name: str | None = None
    type: str  # "opening", "sale", "sale_cancel", "supply", "bleed", "closing"
    amount: float
    balance_after: float
    sale_id: int | None = None
    destination_or_origin: str | None = None
    description: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class CashSessionBrief(BaseModel):
    id: int
    status: str
    opened_at: datetime
    opened_by_user_id: int | None = None
    opened_by_name: str | None = None
    initial_amount: float
    closed_at: datetime | None = None
    closed_by_user_id: int | None = None
    closed_by_name: str | None = None
    expected_closing_amount: float | None = None
    actual_closing_amount: float | None = None
    difference_amount: float | None = None
    closing_notes: str | None = None

    class Config:
        from_attributes = True


class PaymentMethodSummary(BaseModel):
    method: str
    label: str
    total_amount: float
    count: int


class CashSessionDetailResponse(BaseModel):
    session: CashSessionBrief
    cash_register: CashRegisterResponse
    current_balance: float
    total_sales_amount: float
    payment_methods: list[PaymentMethodSummary]
    total_supplies: float
    total_bleeds: float
    movements: list[CashMovementResponse]


class CurrentCashStatusResponse(BaseModel):
    is_open: bool
    current_session: CashSessionDetailResponse | None = None
    last_closed_session: CashSessionDetailResponse | None = None
    suggested_opening_amount: float = 0.0


class CashOpenRequest(BaseModel):
    initial_amount: float = Field(default=0.0, ge=0)
    notes: str | None = None
    cash_register_id: int | None = None


class CashSupplyRequest(BaseModel):
    amount: float = Field(gt=0, description="Valor do suprimento")
    origin: str | None = Field(default="Caixa Administrativo", description="Origem dos recursos")
    description: str = Field(min_length=1, description="Motivo do suprimento")
    cash_register_id: int | None = None


class CashBleedRequest(BaseModel):
    amount: float = Field(gt=0, description="Valor da sangria")
    destination: str | None = Field(default="Caixa Administrativo", description="Destino dos recursos")
    description: str = Field(min_length=1, description="Motivo da sangria")
    cash_register_id: int | None = None


class CashCloseRequest(BaseModel):
    actual_closing_amount: float = Field(ge=0, description="Valor físico contado em dinheiro")
    closing_notes: str | None = None
    cash_register_id: int | None = None
