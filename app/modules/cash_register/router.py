from datetime import date
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    CashRegisterResponse,
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
def get_current_cash_status(request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_current_status(db, tenant_id)


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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_sessions(db, tenant_id, start_date=start_date, end_date=end_date, skip=skip, limit=limit)


@router.get("/sessions/{session_id}", response_model=CashSessionDetailResponse)
def get_cash_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_session_detail(db, tenant_id, session_id)


@router.get("/registers", response_model=List[CashRegisterResponse])
def list_cash_registers(request: Request, db: Session = Depends(get_db)):
    service = CashRegisterService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_registers(db, tenant_id)
