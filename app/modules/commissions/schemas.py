from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal, List
from pydantic import BaseModel


AppliesTo = Literal["service", "product", "both"]
CommissionType = Literal["percentage", "fixed"]
CommissionStatus = Literal["pending", "paid"]


class CommissionRuleBase(BaseModel):
    name: str
    employee_id: Optional[int] = None
    service_id: Optional[int] = None
    applies_to: AppliesTo = "service"
    commission_type: CommissionType
    value: Decimal
    priority: int = 100
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: bool = True


class CommissionRuleCreate(CommissionRuleBase):
    pass


class CommissionRuleUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[int] = None
    service_id: Optional[int] = None
    applies_to: Optional[AppliesTo] = None
    commission_type: Optional[CommissionType] = None
    value: Optional[Decimal] = None
    priority: Optional[int] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None


class CommissionRuleResponse(CommissionRuleBase):
    id: int
    tenant_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CommissionEntryResponse(BaseModel):
    id: int
    tenant_id: int
    sale_id: int
    sale_item_id: int
    employee_id: int
    rule_id: Optional[int]
    commission_type: str
    rate: Decimal
    base_amount: Decimal
    commission_amount: Decimal
    status: CommissionStatus
    paid_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CommissionPayRequest(BaseModel):
    employee_id: int
    entry_ids: List[int]
    notes: Optional[str] = None


class CommissionReportEntry(BaseModel):
    employee_id: int
    employee_name: str
    total_pending: Decimal
    total_paid: Decimal
    entries: List[CommissionEntryResponse]

    class Config:
        from_attributes = True


class AssignEmployeeRequest(BaseModel):
    employee_id: int
