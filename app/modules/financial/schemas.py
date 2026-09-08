from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# ── Contas DRE ─────────────────────────────────────────────────────────────

class DREAccountBase(BaseModel):
    name: str = Field(..., max_length=150)
    code: Optional[str] = Field(None, max_length=50)
    group_type: str = Field(
        ...,
        description="gross_revenue, cmv, fixed_expense, variable_expense, financial_result",
    )
    order_index: int = 0
    is_active: bool = True


class DREAccountCreate(DREAccountBase):
    pass


class DREAccountUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    code: Optional[str] = Field(None, max_length=50)
    group_type: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


class DREAccountResponse(DREAccountBase):
    id: int
    tenant_id: int
    is_system: bool
    system_source: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Lançamentos DRE ────────────────────────────────────────────────────────

class DREEntryUpsert(BaseModel):
    account_id: int
    competence_year: int
    competence_month: int = Field(..., ge=1, le=12)
    amount: float
    notes: Optional[str] = None


class DREEntryBatchUpsert(BaseModel):
    entries: List[DREEntryUpsert]


class DREEntryReplicate(BaseModel):
    account_id: int
    competence_year: int
    start_month: int = Field(1, ge=1, le=12)
    end_month: int = Field(12, ge=1, le=12)
    amount: float
    notes: Optional[str] = None


class DREEntryResponse(BaseModel):
    id: int
    tenant_id: int
    account_id: int
    competence_year: int
    competence_month: int
    amount: float
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Relatório DRE Consolidado ──────────────────────────────────────────────

class DRERowData(BaseModel):
    id: str
    account_id: Optional[int] = None
    name: str
    code: Optional[str] = None
    group_type: str
    is_system: bool = False
    system_source: Optional[str] = None
    is_header: bool = False
    is_subtotal: bool = False
    is_result: bool = False
    is_percentage_row: bool = False
    is_editable: bool = True
    display_order: int = 0
    monthly_amounts: Dict[int, float] = {}  # {1: 1500.0, 2: 1500.0, ...}
    monthly_percentages: Dict[int, float] = {}  # Análise Vertical (% da receita bruta do mês)
    total_amount: float = 0.0
    total_percentage: float = 0.0
    monthly_average: float = 0.0


class DREGroupData(BaseModel):
    group_type: str
    title: str
    subtotal_name: str
    rows: List[DRERowData]
    subtotal_row: DRERowData


class DRESummary(BaseModel):
    gross_revenue_total: float
    cmv_total: float
    gross_margin_total: float
    gross_margin_pct: float
    fixed_expenses_total: float
    variable_expenses_total: float
    ebitda_total: float
    ebitda_pct: float
    financial_result_total: float
    net_profit_total: float
    net_margin_pct: float


class DREReportResponse(BaseModel):
    year: int
    months: List[int]
    groups: List[DREGroupData]
    all_rows: List[DRERowData]
    summary: DRESummary
