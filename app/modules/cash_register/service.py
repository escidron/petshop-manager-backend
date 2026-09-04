from datetime import datetime, date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from .models import CashRegister, CashSession, CashMovement, CashDestinationAccount
from .schemas import (
    CashRegisterResponse,
    CashRegisterCreate,
    CashRegisterUpdate,
    CashDestinationAccountResponse,
    CashDestinationAccountCreate,
    CashDestinationAccountUpdate,
    CashMovementResponse,
    CashSessionBrief,
    PaymentMethodSummary,
    CashSessionDetailResponse,
    CurrentCashStatusResponse,
    CashOpenRequest,
    CashSupplyRequest,
    CashBleedRequest,
    CashCloseRequest,
)
from .repository import CashRegisterRepository
from app.modules.sales.models import Sale


PAYMENT_METHOD_LABELS = {
    "credit_card": "Crédito",
    "debit_card": "Débito",
    "pix": "PIX",
    "money": "Dinheiro",
    "other": "Outros",
    "package": "Pacotes",
}


class CashRegisterService:
    def __init__(self):
        self.repository = CashRegisterRepository()

    def _get_current_balance(self, db: Session, session: CashSession) -> float:
        latest_movement = self.repository.get_latest_movement(db, session.id)
        if latest_movement is not None:
            return float(latest_movement.balance_after)
        return float(session.initial_amount)

    def _auto_close_session(self, db: Session, session: CashSession) -> CashSession:
        current_balance = self._get_current_balance(db, session)
        session.status = "closed"
        # Stamp at 23:59:59 of the date the session was opened
        close_timestamp = datetime.combine(session.opened_at.date(), datetime.max.time().replace(microsecond=0))
        session.closed_at = close_timestamp
        session.expected_closing_amount = current_balance
        session.actual_closing_amount = current_balance
        session.difference_amount = 0.0
        session.closing_notes = "Fechamento automático por virada de dia (23:59)."
        
        # Movement for auto-closing stamped at 23:59:59 of the opened date
        auto_movement = CashMovement(
            tenant_id=session.tenant_id,
            session_id=session.id,
            user_id=session.opened_by_user_id,
            type="closing",
            amount=current_balance,
            balance_after=current_balance,
            description="Fechamento automático por virada de dia.",
            destination_or_origin="Fechamento Automático",
            created_at=close_timestamp,
        )
        self.repository.create_movement(db, auto_movement)
        return self.repository.update_session(db, session)

    def build_session_detail(self, db: Session, tenant_id: int, session: CashSession) -> CashSessionDetailResponse:
        movements = self.repository.list_movements(db, session.id)
        sales = self.repository.list_session_sales(db, tenant_id, session.id)

        # Build payment method summary
        method_totals: dict[str, dict[str, float | int]] = {
            "credit_card": {"total": 0.0, "count": 0},
            "debit_card": {"total": 0.0, "count": 0},
            "pix": {"total": 0.0, "count": 0},
            "money": {"total": 0.0, "count": 0},
            "other": {"total": 0.0, "count": 0},
            "package": {"total": 0.0, "count": 0},
        }

        total_sales_amount = 0.0
        for s in sales:
            if s.payments:
                for p in s.payments:
                    method = p.payment_method if p.payment_method in method_totals else "other"
                    amount = float(p.amount)
                    method_totals[method]["total"] += amount
                    method_totals[method]["count"] += 1
            else:
                method = s.payment_method if s.payment_method in method_totals else "other"
                amount = float(s.total_amount)
                method_totals[method]["total"] += amount
                method_totals[method]["count"] += 1
            total_sales_amount += float(s.total_amount)

        payment_methods: list[PaymentMethodSummary] = []
        for method_key, data in method_totals.items():
            payment_methods.append(
                PaymentMethodSummary(
                    method=method_key,
                    label=PAYMENT_METHOD_LABELS.get(method_key, method_key.capitalize()),
                    total_amount=round(float(data["total"]), 2),
                    count=int(data["count"]),
                )
            )

        total_supplies = sum(float(m.amount) for m in movements if m.type == "supply")
        total_bleeds = sum(float(m.amount) for m in movements if m.type == "bleed")

        current_balance = float(session.actual_closing_amount) if session.status == "closed" and session.actual_closing_amount is not None else self._get_current_balance(db, session)

        movements_resp = [
            CashMovementResponse(
                id=m.id,
                session_id=m.session_id,
                user_id=m.user_id,
                user_name=m.user.name if m.user else "Sistema",
                type=m.type,
                amount=float(m.amount),
                balance_after=float(m.balance_after),
                sale_id=m.sale_id,
                destination_or_origin=m.destination_or_origin,
                description=m.description,
                created_at=m.created_at,
            )
            for m in movements
        ]

        session_brief = CashSessionBrief(
            id=session.id,
            status=session.status,
            opened_at=session.opened_at,
            opened_by_user_id=session.opened_by_user_id,
            opened_by_name=session.opened_by.name if session.opened_by else "Desconhecido",
            initial_amount=float(session.initial_amount),
            closed_at=session.closed_at,
            closed_by_user_id=session.closed_by_user_id,
            closed_by_name=session.closed_by.name if session.closed_by else None,
            expected_closing_amount=float(session.expected_closing_amount) if session.expected_closing_amount is not None else None,
            actual_closing_amount=float(session.actual_closing_amount) if session.actual_closing_amount is not None else None,
            difference_amount=float(session.difference_amount) if session.difference_amount is not None else None,
            closing_notes=session.closing_notes,
        )

        register_resp = CashRegisterResponse(
            id=session.cash_register.id,
            name=session.cash_register.name,
            is_active=session.cash_register.is_active,
            created_at=session.cash_register.created_at,
        )

        return CashSessionDetailResponse(
            session=session_brief,
            cash_register=register_resp,
            current_balance=round(current_balance, 2),
            total_sales_amount=round(total_sales_amount, 2),
            payment_methods=payment_methods,
            total_supplies=round(total_supplies, 2),
            total_bleeds=round(total_bleeds, 2),
            movements=movements_resp,
        )

    def get_current_status(self, db: Session, tenant_id: int, cash_register_id: Optional[int] = None) -> CurrentCashStatusResponse:
        if cash_register_id:
            register = self.repository.get_register_by_id(db, tenant_id, cash_register_id)
            if not register:
                register = self.repository.get_or_create_default_register(db, tenant_id)
        else:
            register = self.repository.get_or_create_default_register(db, tenant_id)

        active_session = self.repository.get_active_session(db, tenant_id, register.id)

        # Check if active session was opened on a previous day and should be auto-closed
        if active_session:
            now = datetime.now()
            # If opened before today's date, auto-close it
            if active_session.opened_at.date() < now.date():
                self._auto_close_session(db, active_session)
                active_session = None

        last_closed = self.repository.get_last_closed_session(db, tenant_id, register.id)

        if active_session:
            current_detail = self.build_session_detail(db, tenant_id, active_session)
            last_closed_detail = self.build_session_detail(db, tenant_id, last_closed) if last_closed else None
            return CurrentCashStatusResponse(
                is_open=True,
                current_session=current_detail,
                last_closed_session=last_closed_detail,
                suggested_opening_amount=float(last_closed.actual_closing_amount or 0.0) if last_closed else 0.0,
            )
        else:
            last_closed_detail = self.build_session_detail(db, tenant_id, last_closed) if last_closed else None
            suggested = float(last_closed.actual_closing_amount or 0.0) if last_closed else 0.0
            return CurrentCashStatusResponse(
                is_open=False,
                current_session=None,
                last_closed_session=last_closed_detail,
                suggested_opening_amount=suggested,
            )

    def open_session(self, db: Session, tenant_id: int, user_id: int, data: CashOpenRequest) -> CashSessionDetailResponse:
        register_id = data.cash_register_id
        if not register_id:
            register = self.repository.get_or_create_default_register(db, tenant_id)
            register_id = register.id
        
        active_session = self.repository.get_active_session(db, tenant_id, register_id)
        if active_session:
            # If from previous date, auto close it
            if active_session.opened_at.date() < datetime.now().date():
                self._auto_close_session(db, active_session)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Já existe uma sessão de caixa aberta para este terminal hoje."
                )

        new_session = CashSession(
            tenant_id=tenant_id,
            cash_register_id=register_id,
            status="open",
            opened_at=datetime.now(),
            opened_by_user_id=user_id,
            initial_amount=data.initial_amount,
            closing_notes=data.notes,
        )
        new_session = self.repository.create_session(db, new_session)

        # Initial opening movement
        initial_movement = CashMovement(
            tenant_id=tenant_id,
            session_id=new_session.id,
            user_id=user_id,
            type="opening",
            amount=data.initial_amount,
            balance_after=data.initial_amount,
            destination_or_origin="Fundo de Troco Inicial",
            description=data.notes or "Abertura Manual de Caixa",
        )
        self.repository.create_movement(db, initial_movement)

        return self.build_session_detail(db, tenant_id, new_session)

    def add_supply(self, db: Session, tenant_id: int, user_id: int, data: CashSupplyRequest) -> CashSessionDetailResponse:
        register_id = data.cash_register_id
        if not register_id:
            register = self.repository.get_or_create_default_register(db, tenant_id)
            register_id = register.id

        active_session = self.repository.get_active_session(db, tenant_id, register_id)
        if active_session and active_session.opened_at.date() < datetime.now().date():
            self._auto_close_session(db, active_session)
            active_session = None

        if not active_session:
            suggested_amount = self.get_current_status(db, tenant_id, register_id).suggested_opening_amount
            active_session = CashSession(
                tenant_id=tenant_id,
                cash_register_id=register_id,
                status="open",
                opened_at=datetime.now(),
                opened_by_user_id=user_id,
                initial_amount=suggested_amount,
                closing_notes="Abertura automática via Suprimento inicial",
            )
            active_session = self.repository.create_session(db, active_session)
            initial_movement = CashMovement(
                tenant_id=tenant_id,
                session_id=active_session.id,
                user_id=user_id,
                type="opening",
                amount=suggested_amount,
                balance_after=suggested_amount,
                destination_or_origin="Fundo de Troco Inicial",
                description="Abertura Automática de Caixa",
            )
            self.repository.create_movement(db, initial_movement)

        current_balance = self._get_current_balance(db, active_session)
        new_balance = current_balance + data.amount

        movement = CashMovement(
            tenant_id=tenant_id,
            session_id=active_session.id,
            user_id=user_id,
            type="supply",
            amount=data.amount,
            balance_after=new_balance,
            destination_or_origin=data.origin or "Caixa Administrativo",
            description=data.description,
        )
        self.repository.create_movement(db, movement)
        return self.build_session_detail(db, tenant_id, active_session)

    def add_bleed(self, db: Session, tenant_id: int, user_id: int, data: CashBleedRequest) -> CashSessionDetailResponse:
        register_id = data.cash_register_id
        if not register_id:
            register = self.repository.get_or_create_default_register(db, tenant_id)
            register_id = register.id

        active_session = self.repository.get_active_session(db, tenant_id, register_id)
        if active_session and active_session.opened_at.date() < datetime.now().date():
            self._auto_close_session(db, active_session)
            active_session = None

        if not active_session:
            suggested_amount = self.get_current_status(db, tenant_id, register_id).suggested_opening_amount
            active_session = CashSession(
                tenant_id=tenant_id,
                cash_register_id=register_id,
                status="open",
                opened_at=datetime.now(),
                opened_by_user_id=user_id,
                initial_amount=suggested_amount,
                closing_notes="Abertura automática via Sangria inicial",
            )
            active_session = self.repository.create_session(db, active_session)
            initial_movement = CashMovement(
                tenant_id=tenant_id,
                session_id=active_session.id,
                user_id=user_id,
                type="opening",
                amount=suggested_amount,
                balance_after=suggested_amount,
                destination_or_origin="Fundo de Troco Inicial",
                description="Abertura Automática de Caixa",
            )
            self.repository.create_movement(db, initial_movement)

        current_balance = self._get_current_balance(db, active_session)
        new_balance = current_balance - data.amount

        movement = CashMovement(
            tenant_id=tenant_id,
            session_id=active_session.id,
            user_id=user_id,
            type="bleed",
            amount=data.amount,
            balance_after=new_balance,
            destination_or_origin=data.destination or "Caixa Administrativo",
            description=data.description,
        )
        self.repository.create_movement(db, movement)
        return self.build_session_detail(db, tenant_id, active_session)

    def close_session(self, db: Session, tenant_id: int, user_id: int, data: CashCloseRequest) -> CashSessionDetailResponse:
        if data.cash_register_id:
            active_session = self.repository.get_active_session(db, tenant_id, data.cash_register_id)
        else:
            active_session = self.repository.get_active_session(db, tenant_id)

        if not active_session:
            raise HTTPException(status_code=400, detail="Nenhum caixa está aberto no momento para ser fechado.")

        expected_balance = self._get_current_balance(db, active_session)
        difference = round(data.actual_closing_amount - expected_balance, 2)

        active_session.status = "closed"
        active_session.closed_at = datetime.now()
        active_session.closed_by_user_id = user_id
        active_session.expected_closing_amount = expected_balance
        active_session.actual_closing_amount = data.actual_closing_amount
        active_session.difference_amount = difference
        active_session.closing_notes = data.closing_notes

        diff_text = f"Diferença: R$ {difference:.2f}" if difference != 0 else "Sem divergência"
        closing_movement = CashMovement(
            tenant_id=tenant_id,
            session_id=active_session.id,
            user_id=user_id,
            type="closing",
            amount=data.actual_closing_amount,
            balance_after=data.actual_closing_amount,
            destination_or_origin="Fechamento de Caixa",
            description=f"Fechamento Manual ({diff_text}). {data.closing_notes or ''}".strip(),
        )
        self.repository.create_movement(db, closing_movement)
        updated_session = self.repository.update_session(db, active_session)

        return self.build_session_detail(db, tenant_id, updated_session)

    def list_sessions(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        cash_register_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[CashSessionDetailResponse]:
        sessions = self.repository.list_sessions(
            db, tenant_id, start_date=start_date, end_date=end_date, cash_register_id=cash_register_id, skip=skip, limit=limit
        )
        return [self.build_session_detail(db, tenant_id, s) for s in sessions]

    def get_session_detail(self, db: Session, tenant_id: int, session_id: int) -> CashSessionDetailResponse:
        session = self.repository.get_session(db, tenant_id, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sessão de caixa não encontrada.")
        return self.build_session_detail(db, tenant_id, session)

    def list_registers(self, db: Session, tenant_id: int, include_inactive: bool = False) -> List[CashRegisterResponse]:
        registers = self.repository.list_registers(db, tenant_id, include_inactive=include_inactive)
        return [
            CashRegisterResponse(
                id=r.id,
                name=r.name,
                is_active=r.is_active,
                created_at=r.created_at,
            )
            for r in registers
        ]

    def create_register(self, db: Session, tenant_id: int, data: CashRegisterCreate) -> CashRegisterResponse:
        register = CashRegister(
            tenant_id=tenant_id,
            name=data.name.strip(),
            is_active=True,
        )
        register = self.repository.create_register(db, register)
        return CashRegisterResponse(
            id=register.id,
            name=register.name,
            is_active=register.is_active,
            created_at=register.created_at,
        )

    def update_register(self, db: Session, tenant_id: int, register_id: int, data: CashRegisterUpdate) -> CashRegisterResponse:
        register = self.repository.get_register_by_id(db, tenant_id, register_id)
        if not register:
            raise HTTPException(status_code=404, detail="Caixa não encontrado.")

        if data.name is not None:
            register.name = data.name.strip()
        if data.is_active is not None:
            register.is_active = data.is_active

        updated = self.repository.update_register(db, register)
        return CashRegisterResponse(
            id=updated.id,
            name=updated.name,
            is_active=updated.is_active,
            created_at=updated.created_at,
        )

    def list_destination_accounts(self, db: Session, tenant_id: int, include_inactive: bool = False) -> List[CashDestinationAccountResponse]:
        accounts = self.repository.list_destination_accounts(db, tenant_id, include_inactive=include_inactive)
        return [
            CashDestinationAccountResponse(
                id=acc.id,
                name=acc.name,
                account_type=acc.account_type,
                is_default=acc.is_default,
                is_active=acc.is_active,
                created_at=acc.created_at,
            )
            for acc in accounts
        ]

    def create_destination_account(self, db: Session, tenant_id: int, data: CashDestinationAccountCreate) -> CashDestinationAccountResponse:
        account = CashDestinationAccount(
            tenant_id=tenant_id,
            name=data.name.strip(),
            account_type=data.account_type,
            is_default=data.is_default,
            is_active=True,
        )
        created = self.repository.create_destination_account(db, account)
        return CashDestinationAccountResponse(
            id=created.id,
            name=created.name,
            account_type=created.account_type,
            is_default=created.is_default,
            is_active=created.is_active,
            created_at=created.created_at,
        )

    def update_destination_account(self, db: Session, tenant_id: int, account_id: int, data: CashDestinationAccountUpdate) -> CashDestinationAccountResponse:
        account = self.repository.get_destination_account_by_id(db, tenant_id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Conta de destino não encontrada.")

        if data.name is not None:
            account.name = data.name.strip()
        if data.account_type is not None:
            account.account_type = data.account_type
        if data.is_default is not None:
            account.is_default = data.is_default
        if data.is_active is not None:
            account.is_active = data.is_active

        updated = self.repository.update_destination_account(db, account)
        return CashDestinationAccountResponse(
            id=updated.id,
            name=updated.name,
            account_type=updated.account_type,
            is_default=updated.is_default,
            is_active=updated.is_active,
            created_at=updated.created_at,
        )

    def delete_destination_account(self, db: Session, tenant_id: int, account_id: int) -> dict:
        account = self.repository.get_destination_account_by_id(db, tenant_id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Conta de destino não encontrada.")
        
        # If default, don't allow deletion if it's the only one
        accounts = self.repository.list_destination_accounts(db, tenant_id, include_inactive=True)
        if len(accounts) <= 1:
            raise HTTPException(status_code=400, detail="Você deve manter pelo menos uma conta cadastrada.")

        self.repository.delete_destination_account(db, account)
        return {"detail": "Conta de destino removida com sucesso."}
