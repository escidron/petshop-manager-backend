from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional

from .models import CashRegister, CashSession, CashMovement
from app.modules.sales.models import Sale


class CashRegisterRepository:
    def get_or_create_default_register(self, db: Session, tenant_id: int) -> CashRegister:
        register = (
            db.query(CashRegister)
            .filter(CashRegister.tenant_id == tenant_id, CashRegister.is_active == True)
            .first()
        )
        if not register:
            register = CashRegister(
                tenant_id=tenant_id,
                name="Caixa Principal",
                is_active=True
            )
            db.add(register)
            db.commit()
            db.refresh(register)
        return register

    def list_registers(self, db: Session, tenant_id: int) -> List[CashRegister]:
        registers = (
            db.query(CashRegister)
            .filter(CashRegister.tenant_id == tenant_id, CashRegister.is_active == True)
            .order_by(CashRegister.id.asc())
            .all()
        )
        if not registers:
            return [self.get_or_create_default_register(db, tenant_id)]
        return registers

    def get_active_session(self, db: Session, tenant_id: int, cash_register_id: Optional[int] = None) -> Optional[CashSession]:
        query = (
            db.query(CashSession)
            .options(
                joinedload(CashSession.opened_by),
                joinedload(CashSession.closed_by),
                joinedload(CashSession.cash_register),
            )
            .filter(CashSession.tenant_id == tenant_id, CashSession.status == "open")
        )
        if cash_register_id:
            query = query.filter(CashSession.cash_register_id == cash_register_id)
        
        return query.order_by(CashSession.opened_at.desc()).first()

    def get_last_closed_session(self, db: Session, tenant_id: int, cash_register_id: Optional[int] = None) -> Optional[CashSession]:
        query = (
            db.query(CashSession)
            .options(
                joinedload(CashSession.opened_by),
                joinedload(CashSession.closed_by),
                joinedload(CashSession.cash_register),
            )
            .filter(CashSession.tenant_id == tenant_id, CashSession.status == "closed")
        )
        if cash_register_id:
            query = query.filter(CashSession.cash_register_id == cash_register_id)
        
        return query.order_by(CashSession.closed_at.desc()).first()

    def get_session(self, db: Session, tenant_id: int, session_id: int) -> Optional[CashSession]:
        return (
            db.query(CashSession)
            .options(
                joinedload(CashSession.opened_by),
                joinedload(CashSession.closed_by),
                joinedload(CashSession.cash_register),
            )
            .filter(CashSession.tenant_id == tenant_id, CashSession.id == session_id)
            .first()
        )

    def create_session(self, db: Session, session: CashSession) -> CashSession:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def update_session(self, db: Session, session: CashSession) -> CashSession:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def create_movement(self, db: Session, movement: CashMovement) -> CashMovement:
        db.add(movement)
        db.commit()
        db.refresh(movement)
        return movement

    def get_latest_movement(self, db: Session, session_id: int) -> Optional[CashMovement]:
        return (
            db.query(CashMovement)
            .filter(CashMovement.session_id == session_id)
            .order_by(CashMovement.id.desc())
            .first()
        )

    def list_movements(self, db: Session, session_id: int) -> List[CashMovement]:
        return (
            db.query(CashMovement)
            .options(joinedload(CashMovement.user), joinedload(CashMovement.sale))
            .filter(CashMovement.session_id == session_id)
            .order_by(CashMovement.created_at.desc(), CashMovement.id.desc())
            .all()
        )

    def list_session_sales(self, db: Session, tenant_id: int, session_id: int) -> List[Sale]:
        return (
            db.query(Sale)
            .filter(
                Sale.tenant_id == tenant_id,
                Sale.cash_session_id == session_id,
                Sale.status == "completed"
            )
            .all()
        )

    def list_sessions(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[CashSession]:
        query = (
            db.query(CashSession)
            .options(
                joinedload(CashSession.opened_by),
                joinedload(CashSession.closed_by),
                joinedload(CashSession.cash_register),
            )
            .filter(CashSession.tenant_id == tenant_id)
        )

        if start_date:
            query = query.filter(func.date(CashSession.opened_at) >= start_date)
        if end_date:
            query = query.filter(func.date(CashSession.opened_at) <= end_date)

        return query.order_by(CashSession.opened_at.desc()).offset(skip).limit(limit).all()
