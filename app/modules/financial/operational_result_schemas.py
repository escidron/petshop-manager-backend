from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class OperationalDayMeta(BaseModel):
    day: int
    day_of_week: str  # ex: "SÁB", "DOM", "SEG"
    date_str: str  # ex: "01/jul"
    is_weekend: bool  # Mantido para retrocompatibilidade
    is_closed: bool = False  # True quando o estabelecimento está fechado na configuração do tenant
    has_activity: bool = False


class OperationalServiceRow(BaseModel):
    code: str  # ex: "BP", "BM", "MP", "TP", "BGA"
    name: str  # ex: "Banho P", "Máq. P", "Tes. P"
    group_key: str  # "bath", "machine", "scissor", "cat", "other"
    group_name: str  # "Banhos", "Tosa Máquina", "Tosa Tesoura", "Gatos", "Outros"
    daily_counts: Dict[int, int] = Field(default_factory=dict)
    total_count: int = 0
    order_index: int = 0


class OperationalGroupSubtotal(BaseModel):
    group_key: str
    group_name: str
    daily_counts: Dict[int, int] = Field(default_factory=dict)
    total_count: int = 0


class OperationalSummaryKPIs(BaseModel):
    total_services: int = 0
    working_days: int = 0
    avg_services_per_working_day: float = 0.0
    peak_day: int = 0
    peak_day_count: int = 0
    peak_day_label: str = ""
    top_service_name: str = "-"
    top_service_count: int = 0
    top_service_pct: float = 0.0
    total_revenue: float = 0.0
    avg_revenue_per_working_day: float = 0.0
    ticket_medio_operational: float = 0.0


class OperationalAnnualComparison(BaseModel):
    current_year: int
    previous_year: int
    monthly_volume_current: Dict[int, int] = Field(default_factory=dict)  # 1..12 -> volume
    monthly_volume_previous: Dict[int, int] = Field(default_factory=dict)  # 1..12 -> volume


class OperationalStratifiedItem(BaseModel):
    code: str
    name: str
    group_key: str
    count: int
    percentage: float


class OperationalResultResponse(BaseModel):
    year: int
    month: int
    days_in_month: int
    days_metadata: List[OperationalDayMeta]
    rows: List[OperationalServiceRow]
    group_subtotals: List[OperationalGroupSubtotal]
    daily_totals: Dict[int, int]
    summary: OperationalSummaryKPIs
    annual_comparison: OperationalAnnualComparison
    stratified_services: List[OperationalStratifiedItem]
