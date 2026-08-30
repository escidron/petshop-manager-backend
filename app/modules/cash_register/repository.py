from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional

from .models import CashRegister, CashSession, CashMovement, CashDestinationAccount
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

    def list_registers(self, db: Session, tenant_id: int, include_inactive: bool = False) -> List[CashRegister]:
        query = db.query(CashRegister).filter(CashRegister.tenant_id == tenant_id)
        if not include_inactive:
            query = query.filter(CashRegister.is_active == True)
        
        registers = query.order_by(CashRegister.id.asc()).all()
        if not registers and not include_inactive:
            return [self.get_or_create_default_register(db, tenant_id)]
        return registers

    def create_register(self, db: Session, register: CashRegister) -> CashRegister:
        db.add(register)
        db.commit()
        db.refresh(register)
        return register

    def get_register_by_id(self, db: Session, tenant_id: int, register_id: int) -> Optional[CashRegister]:
        return (
            db.query(CashRegister)
            .filter(CashRegister.id == register_id, CashRegister.tenant_id == tenant_id)
            .first()
        )

    def update_register(self, db: Session, register: CashRegister) -> CashRegister:
        db.commit()
        db.refresh(register)
        return register

    def get_or_create_default_destination_account(self, db: Session, tenant_id: int) -> CashDestinationAccount:
        acc = (
            db.query(CashDestinationAccount)
            .filter(CashDestinationAccount.tenant_id == tenant_id, CashDestinationAccount.is_active == True)
            .first()
        )
        if not acc:
            acc = CashDestinationAccount(
                tenant_id=tenant_id,
                name="Caixa Administrativo",
                account_type="internal_cash",
                is_default=True,
                is_active=True,
            )
            db.add(acc)
            db.commit()
            db.refresh(acc)
        return acc

    def list_destination_accounts(self, db: Session, tenant_id: int, include_inactive: bool = False) -> List[CashDestinationAccount]:
        query = db.query(CashDestinationAccount).filter(CashDestinationAccount.tenant_id == tenant_id)
        if not include_inactive:
            query = query.filter(CashDestinationAccount.is_active == True)
        
        accounts = query.order_by(CashDestinationAccount.is_default.desc(), CashDestinationAccount.name.asc()).all()
        if not accounts and not include_inactive:
            return [self.get_or_create_default_destination_account(db, tenant_id)]
        return accounts

    def create_destination_account(self, db: Session, account: CashDestinationAccount) -> CashDestinationAccount:
        if account.is_default:
            db.query(CashDestinationAccount).filter(
                CashDestinationAccount.tenant_id == account.tenant_id
            ).update({"is_default": False})
        db.add(account)
        db.commit()
        db.refresh(account)
        return account

    def get_destination_account_by_id(self, db: Session, tenant_id: int, account_id: int) -> Optional[CashDestinationAccount]:
        return (
            db.query(CashDestinationAccount)
            .filter(CashDestinationAccount.id == account_id, CashDestinationAccount.tenant_id == tenant_id)
            .first()
        )

    def update_destination_account(self, db: Session, account: CashDestinationAccount) -> CashDestinationAccount:
        if account.is_default:
            db.query(CashDestinationAccount).filter(
                CashDestinationAccount.tenant_id == account.tenant_id,
                CashDestinationAccount.id != account.id
            ).update({"is_default": False})
        db.commit()
        db.refresh(account)
        return account

    def delete_destination_account(self, db: Session, account: CashDestinationAccount) -> None:
        db.delete(account)
        db.commit()

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
        cash_register_id: Optional[int] = None,
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

        if cash_register_id:
            query = query.filter(CashSession.cash_register_id == cash_register_id)
        if start_date:
            query = query.filter(func.date(CashSession.opened_at) >= start_date)
        if end_date:
            query = query.filter(func.date(CashSession.opened_at) <= end_date)

        return query.order_by(CashSession.opened_at.desc()).offset(skip).limit(limit).all()
