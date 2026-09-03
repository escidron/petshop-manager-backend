from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal, List
from pydantic import BaseModel, model_validator


AppliesTo = Literal["service", "product", "both"]
CommissionType = Literal["percentage", "fixed"]
CommissionStatus = Literal["pending", "paid"]


class CommissionRuleEmployeeInfo(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class CommissionRuleServiceInfo(BaseModel):
    id: int
    name: str
    species: Optional[str] = None
    size: Optional[str] = None
    coat_type: Optional[str] = None

    class Config:
        from_attributes = True


class CommissionRuleBase(BaseModel):
    name: str
    employee_id: Optional[int] = None
    employee_ids: List[int] = []
    service_ids: List[int] = []
    applies_to: AppliesTo = "service"
    commission_type: CommissionType
    value: Decimal
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: bool = True


class CommissionRuleCreate(CommissionRuleBase):
    pass


class CommissionRuleUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[int] = None
    employee_ids: Optional[List[int]] = None  # None = não altera; [] = limpa todos
    service_ids: Optional[List[int]] = None  # None = não altera; [] = limpa todos
    applies_to: Optional[AppliesTo] = None
    commission_type: Optional[CommissionType] = None
    value: Optional[Decimal] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None


class CommissionRuleResponse(CommissionRuleBase):
    id: int
    tenant_id: int
    created_at: datetime
    employee_name: Optional[str] = None
    employees: List[CommissionRuleEmployeeInfo] = []
    services: List[CommissionRuleServiceInfo] = []

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def populate_relations(cls, data):
        if isinstance(data, dict):
            return data
        employees = getattr(data, "employees", [])
        employee_names = [e.name for e in employees] if employees else []
        employee_name = ", ".join(employee_names) if employee_names else None
        employee_ids = [e.id for e in employees]
        services = getattr(data, "services", [])
        return {
            "id": data.id,
            "tenant_id": data.tenant_id,
            "name": data.name,
            "employee_id": employee_ids[0] if employee_ids else None,
            "employee_ids": employee_ids,
            "employee_name": employee_name,
            "employees": employees,
            "service_ids": [s.id for s in services],
            "services": services,
            "applies_to": data.applies_to,
            "commission_type": data.commission_type,
            "value": data.value,
            "valid_from": data.valid_from,
            "valid_until": data.valid_until,
            "is_active": data.is_active,
            "created_at": data.created_at,
        }



class CommissionEntryResponse(BaseModel):
    id: int
    tenant_id: int
    sale_id: Optional[int] = None
    sale_item_id: Optional[int] = None
    appointment_item_id: Optional[int] = None
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


class AssignEmployeeRequest(BaseModel):
    employee_id: int
