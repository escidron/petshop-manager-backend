from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CustomBenefitItem(BaseModel):
    name: str
    amount: float = Field(default=0.0, ge=0.0)


class PayrollProfileBase(BaseModel):
    base_salary: float = Field(default=0.0, ge=0.0)
    thirteenth_salary: float = Field(default=0.0, ge=0.0)
    vacation_provision: float = Field(default=0.0, ge=0.0)
    fgts_amount: float = Field(default=0.0, ge=0.0)
    inss_amount: float = Field(default=0.0, ge=0.0)

    # Granularidade de Benefícios
    transport_voucher: float = Field(default=0.0, ge=0.0)
    food_voucher: float = Field(default=0.0, ge=0.0)
    meal_voucher: float = Field(default=0.0, ge=0.0)
    health_insurance: float = Field(default=0.0, ge=0.0)
    other_benefits: float = Field(default=0.0, ge=0.0)
    other_benefits_description: Optional[str] = None
    custom_benefits: Optional[List[CustomBenefitItem]] = None

    notes: Optional[str] = None
    is_active: bool = True


class PayrollProfileUpdate(BaseModel):
    base_salary: Optional[float] = Field(default=None, ge=0.0)
    thirteenth_salary: Optional[float] = Field(default=None, ge=0.0)
    vacation_provision: Optional[float] = Field(default=None, ge=0.0)
    fgts_amount: Optional[float] = Field(default=None, ge=0.0)
    inss_amount: Optional[float] = Field(default=None, ge=0.0)

    transport_voucher: Optional[float] = Field(default=None, ge=0.0)
    food_voucher: Optional[float] = Field(default=None, ge=0.0)
    meal_voucher: Optional[float] = Field(default=None, ge=0.0)
    health_insurance: Optional[float] = Field(default=None, ge=0.0)
    other_benefits: Optional[float] = Field(default=None, ge=0.0)
    other_benefits_description: Optional[str] = None
    custom_benefits: Optional[List[CustomBenefitItem]] = None

    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PayrollProfileResponse(PayrollProfileBase):
    id: Optional[int] = None
    employee_id: int
    employee_name: str
    employee_role: str
    employee_is_active: bool

    # Campos Computados
    total_salaries_and_provisions: float = 0.0
    total_inss: float = 0.0
    total_fgts: float = 0.0
    total_benefits: float = 0.0
    total_monthly_cost: float = 0.0
    overhead_percentage: float = 0.0

    class Config:
        from_attributes = True


class PayrollSummaryResponse(BaseModel):
    total_base_salary: float = 0.0
    total_thirteenth: float = 0.0
    total_vacation: float = 0.0
    total_salaries_and_provisions: float = 0.0
    total_inss: float = 0.0
    total_fgts: float = 0.0
    total_charges: float = 0.0
    total_transport_voucher: float = 0.0
    total_food_voucher: float = 0.0
    total_meal_voucher: float = 0.0
    total_health_insurance: float = 0.0
    total_other_benefits: float = 0.0
    total_benefits: float = 0.0
    total_monthly_cost: float = 0.0
    total_annual_cost: float = 0.0
    active_employees_count: int = 0


class PayrollSyncToDRERequest(BaseModel):
    year: int
    months: List[int] = Field(default_factory=lambda: list(range(1, 13)))
    # { "salaries": account_id, "inss": account_id, "fgts": account_id, "benefits": account_id }
    account_mapping: Optional[Dict[str, int]] = None


class PayrollSyncResponse(BaseModel):
    success: bool
    message: str
    year: int
    months_updated: List[int]
    entries_created_or_updated: int
    accounts_used: Dict[str, Any]
