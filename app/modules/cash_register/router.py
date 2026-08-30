from datetime import date
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    CashRegisterResponse,
    CashRegisterCreate,
    CashRegisterUpdate,
    CashDestinationAccountResponse,
    CashDestinationAccountCreate,
    CashDestinationAccountUpdate,
    CashSessionDetailResponse,
    CurrentCashStatusResponse,
    CashOpenRequest,
    CashSupplyRequest,
    CashBleedRequest,
    CashCloseRequest,
)
from .service import CashRegisterService

router = APIRouter(prefix="/cash", tags=["Frente de Caixa / PDV"], dependencies=[Depends(get_current_tenant)])


@router.get("/current", response_model=CurrentCashStatusResponse)
def get_current_cash_status(
    request: Request,
    db: Session = Depends(get_db),
    cash_register_id: Optional[int] = Query(None),
):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_current_status(db, tenant_id, cash_register_id=cash_register_id)


@router.post("/open", response_model=CashSessionDetailResponse, dependencies=[Depends(require_active_subscription)])
def open_cash_session(data: CashOpenRequest, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    return service.open_session(db, tenant_id, user_id, data)


@router.post("/supply", response_model=CashSessionDetailResponse, dependencies=[Depends(require_active_subscription)])
def add_cash_supply(data: CashSupplyRequest, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    return service.add_supply(db, tenant_id, user_id, data)


@router.post("/bleed", response_model=CashSessionDetailResponse, dependencies=[Depends(require_active_subscription)])
def add_cash_bleed(data: CashBleedRequest, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    return service.add_bleed(db, tenant_id, user_id, data)


@router.post("/close", response_model=CashSessionDetailResponse, dependencies=[Depends(require_active_subscription)])
def close_cash_session(data: CashCloseRequest, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    return service.close_session(db, tenant_id, user_id, data)


@router.get("/sessions", response_model=List[CashSessionDetailResponse])
def list_cash_sessions(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    cash_register_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_sessions(
        db, tenant_id, start_date=start_date, end_date=end_date, cash_register_id=cash_register_id, skip=skip, limit=limit
    )


@router.get("/sessions/{session_id}", response_model=CashSessionDetailResponse)
def get_cash_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_session_detail(db, tenant_id, session_id)


# ── Terminais de Caixa ───────────────────────────────────────────────────────
@router.get("/registers", response_model=List[CashRegisterResponse])
def list_cash_registers(
    request: Request,
    db: Session = Depends(get_db),
    include_inactive: bool = Query(False),
):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_registers(db, tenant_id, include_inactive=include_inactive)


@router.post("/registers", response_model=CashRegisterResponse, dependencies=[Depends(require_active_subscription)])
def create_cash_register(data: CashRegisterCreate, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_register(db, tenant_id, data)


@router.put("/registers/{register_id}", response_model=CashRegisterResponse, dependencies=[Depends(require_active_subscription)])
def update_cash_register(register_id: int, data: CashRegisterUpdate, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_register(db, tenant_id, register_id, data)


# ── Contas de Destino / Origem ───────────────────────────────────────────────
@router.get("/destination-accounts", response_model=List[CashDestinationAccountResponse])
def list_destination_accounts(
    request: Request,
    db: Session = Depends(get_db),
    include_inactive: bool = Query(False),
):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_destination_accounts(db, tenant_id, include_inactive=include_inactive)


@router.post("/destination-accounts", response_model=CashDestinationAccountResponse, dependencies=[Depends(require_active_subscription)])
def create_destination_account(data: CashDestinationAccountCreate, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_destination_account(db, tenant_id, data)


@router.put("/destination-accounts/{account_id}", response_model=CashDestinationAccountResponse, dependencies=[Depends(require_active_subscription)])
def update_destination_account(account_id: int, data: CashDestinationAccountUpdate, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_destination_account(db, tenant_id, account_id, data)


@router.delete("/destination-accounts/{account_id}", dependencies=[Depends(require_active_subscription)])
def delete_destination_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.delete_destination_account(db, tenant_id, account_id)

