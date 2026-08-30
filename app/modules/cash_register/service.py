from datetime import datetime, date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from .models import CashRegister, CashSession, CashMovement
from .schemas import (
    CashRegisterResponse,
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
        session.closed_at = datetime.now()
        session.expected_closing_amount = current_balance
        session.actual_closing_amount = current_balance
        session.difference_amount = 0.0
        session.closing_notes = "Fechamento automático por virada de turno/dia."
        
        # Movement for auto-closing
        auto_movement = CashMovement(
            tenant_id=session.tenant_id,
            session_id=session.id,
            user_id=session.opened_by_user_id,
            type="closing",
            amount=current_balance,
            balance_after=current_balance,
            description="Fechamento automático por virada de dia.",
            destination_or_origin="Fechamento Automático",
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
            method = s.payment_method if s.payment_method in method_totals else "other"
            amount = float(s.total_amount)
            method_totals[method]["total"] += amount
            method_totals[method]["count"] += 1
            total_sales_amount += amount

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

    def get_current_status(self, db: Session, tenant_id: int) -> CurrentCashStatusResponse:
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
        active_session = self.repository.get_active_session(db, tenant_id)
        if active_session and active_session.opened_at.date() < datetime.now().date():
            self._auto_close_session(db, active_session)
            active_session = None

        if not active_session:
            suggested_amount = self.get_current_status(db, tenant_id).suggested_opening_amount
            register = self.repository.get_or_create_default_register(db, tenant_id)
            active_session = CashSession(
                tenant_id=tenant_id,
                cash_register_id=register.id,
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
        active_session = self.repository.get_active_session(db, tenant_id)
        if active_session and active_session.opened_at.date() < datetime.now().date():
            self._auto_close_session(db, active_session)
            active_session = None

        if not active_session:
            suggested_amount = self.get_current_status(db, tenant_id).suggested_opening_amount
            register = self.repository.get_or_create_default_register(db, tenant_id)
            active_session = CashSession(
                tenant_id=tenant_id,
                cash_register_id=register.id,
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
        skip: int = 0,
        limit: int = 50,
    ) -> List[CashSessionDetailResponse]:
        sessions = self.repository.list_sessions(db, tenant_id, start_date=start_date, end_date=end_date, skip=skip, limit=limit)
        return [self.build_session_detail(db, tenant_id, s) for s in sessions]

    def get_session_detail(self, db: Session, tenant_id: int, session_id: int) -> CashSessionDetailResponse:
        session = self.repository.get_session(db, tenant_id, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sessão de caixa não encontrada.")
        return self.build_session_detail(db, tenant_id, session)

    def list_registers(self, db: Session, tenant_id: int) -> List[CashRegisterResponse]:
        registers = self.repository.list_registers(db, tenant_id)
        return [
            CashRegisterResponse(
                id=r.id,
                name=r.name,
                is_active=r.is_active,
                created_at=r.created_at,
            )
            for r in registers
        ]
