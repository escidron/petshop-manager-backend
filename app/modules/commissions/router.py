from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import (
    CommissionRuleCreate,
    CommissionRuleUpdate,
    CommissionRuleResponse,
    CommissionEntryResponse,
    CommissionPayRequest,
)
from .service import CommissionService

router = APIRouter(
    prefix="/commissions",
    tags=["Commissions"],
    dependencies=[Depends(get_current_tenant)],
)

service = CommissionService()


# ── Rules ─────────────────────────────────────────────────────────────────────

@router.post("/rules/", response_model=CommissionRuleResponse)
def create_rule(data: CommissionRuleCreate, request: Request, db: Session = Depends(get_db)):
    return service.create_rule(db, request.state.tenant_user.tenant_id, data)


@router.get("/rules/", response_model=list[CommissionRuleResponse])
def list_rules(request: Request, db: Session = Depends(get_db)):
    return service.list_rules(db, request.state.tenant_user.tenant_id)


@router.get("/rules/{rule_id}", response_model=CommissionRuleResponse)
def get_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    return service.get_rule(db, request.state.tenant_user.tenant_id, rule_id)


@router.patch("/rules/{rule_id}", response_model=CommissionRuleResponse)
def update_rule(rule_id: int, data: CommissionRuleUpdate, request: Request, db: Session = Depends(get_db)):
    return service.update_rule(db, request.state.tenant_user.tenant_id, rule_id, data)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    service.delete_rule(db, request.state.tenant_user.tenant_id, rule_id)


# ── Entries / Report ──────────────────────────────────────────────────────────

@router.get("/entries/", response_model=list[CommissionEntryResponse])
def list_entries(
    request: Request,
    db: Session = Depends(get_db),
    employee_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    return service.list_entries(
        db,
        request.state.tenant_user.tenant_id,
        employee_id=employee_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )


@router.post("/pay/", response_model=list[CommissionEntryResponse])
def pay_entries(data: CommissionPayRequest, request: Request, db: Session = Depends(get_db)):
    return service.pay_entries(db, request.state.tenant_user.tenant_id, data)
