from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict


class FinancialBillBase(BaseModel):
    bill_type: Literal["payable", "receivable"]
    description: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    due_date: date
    issue_date: Optional[date] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    client_id: Optional[int] = None
    payment_method: Optional[str] = None
    document_number: Optional[str] = None
    barcode: Optional[str] = None
    notes: Optional[str] = None


class FinancialBillCreate(FinancialBillBase):
    total_installments: Optional[int] = Field(default=1, ge=1, le=60)
    installment_interval_days: Optional[int] = Field(default=30, ge=1, le=365)


class FinancialBillUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=255)
    amount: Optional[float] = Field(default=None, gt=0)
    due_date: Optional[date] = None
    issue_date: Optional[date] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    client_id: Optional[int] = None
    payment_method: Optional[str] = None
    document_number: Optional[str] = None
    barcode: Optional[str] = None
    notes: Optional[str] = None


class FinancialBillSettle(BaseModel):
    payment_date: date = Field(default_factory=date.today)
    paid_amount: float = Field(..., ge=0)
    discount_amount: Optional[float] = Field(default=0.0, ge=0)
    fine_or_interest_amount: Optional[float] = Field(default=0.0, ge=0)
    payment_method: Optional[str] = None
    destination_account_id: Optional[int] = None
    notes: Optional[str] = None


class FinancialBillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    bill_type: str
    description: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    sale_id: Optional[int] = None
    amount: float
    paid_amount: float
    discount_amount: float
    fine_or_interest_amount: float
    issue_date: date
    due_date: date
    payment_date: Optional[date] = None
    status: str
    payment_method: Optional[str] = None
    document_number: Optional[str] = None
    barcode: Optional[str] = None
    installment_number: int
    total_installments: int
    parent_bill_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FinancialBillsSummaryResponse(BaseModel):
    total_payable: float = 0.0
    payable_paid: float = 0.0
    payable_pending: float = 0.0
    payable_overdue: float = 0.0
    payable_overdue_count: int = 0

    total_receivable: float = 0.0
    receivable_paid: float = 0.0
    receivable_pending: float = 0.0
    receivable_overdue: float = 0.0
    receivable_overdue_count: int = 0

    net_balance_projected: float = 0.0
    net_balance_realized: float = 0.0
    net_balance_pending: float = 0.0
    net_balance_expected: float = 0.0


class FinancialBillListResponse(BaseModel):
    items: List[FinancialBillResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
