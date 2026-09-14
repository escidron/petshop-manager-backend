from datetime import date
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, desc, asc, case

from app.modules.financial.models import FinancialBill, DREAccount
from app.modules.suppliers.models import Supplier
from app.modules.clients.models import Client
from app.modules.financial.bills_schemas import (
    FinancialBillCreate,
    FinancialBillUpdate,
    FinancialBillSettle,
    FinancialBillsSummaryResponse,
)


class FinancialBillsRepository:
    def _apply_overdue_status(self, bill: FinancialBill, today: date) -> str:
        """Determina dinamicamente se a conta pendente está vencida."""
        if bill.status == "pending" and bill.due_date < today:
            return "overdue"
        return bill.status

    def get_bills(
        self,
        db: Session,
        tenant_id: int,
        bill_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        client_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "due_date",
        sort_dir: str = "asc",
    ) -> Tuple[List[FinancialBill], int]:
        today = date.today()
        query = (
            db.query(FinancialBill)
            .options(
                joinedload(FinancialBill.category),
                joinedload(FinancialBill.supplier),
                joinedload(FinancialBill.client),
            )
            .filter(FinancialBill.tenant_id == tenant_id)
        )

        if bill_type and bill_type in ("payable", "receivable"):
            query = query.filter(FinancialBill.bill_type == bill_type)

        if status:
            if status == "overdue":
                query = query.filter(
                    and_(
                        FinancialBill.status == "pending",
                        FinancialBill.due_date < today,
                    )
                )
            elif status == "pending":
                query = query.filter(
                    and_(
                        FinancialBill.status == "pending",
                        FinancialBill.due_date >= today,
                    )
                )
            else:
                query = query.filter(FinancialBill.status == status)

        if start_date:
            query = query.filter(FinancialBill.due_date >= start_date)
        if end_date:
            query = query.filter(FinancialBill.due_date <= end_date)

        if category_id:
            query = query.filter(FinancialBill.category_id == category_id)
        if supplier_id:
            query = query.filter(FinancialBill.supplier_id == supplier_id)
        if client_id:
            query = query.filter(FinancialBill.client_id == client_id)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    FinancialBill.description.ilike(term),
                    FinancialBill.document_number.ilike(term),
                    FinancialBill.barcode.ilike(term),
                )
            )

        total = query.count()

        # Ordenação
        sort_column = getattr(FinancialBill, sort_by, FinancialBill.due_date)
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column), desc(FinancialBill.id))
        else:
            query = query.order_by(asc(sort_column), asc(FinancialBill.id))

        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        # Ajusta status dinâmico para overdue
        for item in items:
            item.status = self._apply_overdue_status(item, today)

        return items, total

    def get_summary(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
    ) -> FinancialBillsSummaryResponse:
        today = date.today()
        query = db.query(FinancialBill).filter(
            and_(
                FinancialBill.tenant_id == tenant_id,
                FinancialBill.status != "canceled",
            )
        )

        if start_date:
            query = query.filter(FinancialBill.due_date >= start_date)
        if end_date:
            query = query.filter(FinancialBill.due_date <= end_date)
        if category_id:
            query = query.filter(FinancialBill.category_id == category_id)

        bills = query.all()

        total_payable = 0.0
        payable_paid = 0.0
        payable_pending = 0.0
        payable_overdue = 0.0
        payable_overdue_count = 0

        total_receivable = 0.0
        receivable_paid = 0.0
        receivable_pending = 0.0
        receivable_overdue = 0.0
        receivable_overdue_count = 0

        for b in bills:
            amt = float(b.amount or 0.0)
            paid = float(b.paid_amount or 0.0)
            is_overdue = b.status == "pending" and b.due_date < today

            if b.bill_type == "payable":
                total_payable += amt
                if b.status == "paid":
                    payable_paid += paid if paid > 0 else amt
                elif is_overdue:
                    payable_overdue += amt
                    payable_overdue_count += 1
                else:
                    payable_pending += amt
            elif b.bill_type == "receivable":
                total_receivable += amt
                if b.status == "paid":
                    receivable_paid += paid if paid > 0 else amt
                elif is_overdue:
                    receivable_overdue += amt
                    receivable_overdue_count += 1
                else:
                    receivable_pending += amt

        # Saldo previsto = (receitas pendentes + vencidas) - (despesas pendentes + vencidas)
        net_balance_expected = (receivable_pending + receivable_overdue) - (payable_pending + payable_overdue)
        net_balance_realized = receivable_paid - payable_paid

        return FinancialBillsSummaryResponse(
            total_payable=round(total_payable, 2),
            payable_paid=round(payable_paid, 2),
            payable_pending=round(payable_pending, 2),
            payable_overdue=round(payable_overdue, 2),
            payable_overdue_count=payable_overdue_count,
            total_receivable=round(total_receivable, 2),
            receivable_paid=round(receivable_paid, 2),
            receivable_pending=round(receivable_pending, 2),
            receivable_overdue=round(receivable_overdue, 2),
            receivable_overdue_count=receivable_overdue_count,
            net_balance_expected=round(net_balance_expected, 2),
            net_balance_realized=round(net_balance_realized, 2),
        )

    def get_bill(self, db: Session, tenant_id: int, bill_id: int) -> Optional[FinancialBill]:
        today = date.today()
        bill = (
            db.query(FinancialBill)
            .options(
                joinedload(FinancialBill.category),
                joinedload(FinancialBill.supplier),
                joinedload(FinancialBill.client),
            )
            .filter(
                FinancialBill.id == bill_id,
                FinancialBill.tenant_id == tenant_id,
            )
            .first()
        )
        if bill:
            bill.status = self._apply_overdue_status(bill, today)
        return bill

    def create_bill(self, db: Session, bill: FinancialBill) -> FinancialBill:
        db.add(bill)
        db.commit()
        db.refresh(bill)
        return bill

    def create_bills_batch(self, db: Session, bills: List[FinancialBill]) -> List[FinancialBill]:
        db.add_all(bills)
        db.commit()
        for b in bills:
            db.refresh(b)
        return bills

    def update_bill(
        self, db: Session, tenant_id: int, bill_id: int, data: FinancialBillUpdate
    ) -> Optional[FinancialBill]:
        bill = (
            db.query(FinancialBill)
            .filter(
                FinancialBill.id == bill_id,
                FinancialBill.tenant_id == tenant_id,
            )
            .first()
        )
        if not bill:
            return None

        update_dict = data.model_dump(exclude_unset=True)
        for key, val in update_dict.items():
            setattr(bill, key, val)

        db.commit()
        db.refresh(bill)
        bill.status = self._apply_overdue_status(bill, date.today())
        return bill

    def settle_bill(
        self, db: Session, tenant_id: int, bill_id: int, data: FinancialBillSettle
    ) -> Optional[FinancialBill]:
        bill = (
            db.query(FinancialBill)
            .filter(
                FinancialBill.id == bill_id,
                FinancialBill.tenant_id == tenant_id,
            )
            .first()
        )
        if not bill:
            return None

        bill.status = "paid"
        bill.payment_date = data.payment_date
        bill.paid_amount = data.paid_amount
        bill.discount_amount = data.discount_amount or 0.0
        bill.fine_or_interest_amount = data.fine_or_interest_amount or 0.0
        if data.payment_method:
            bill.payment_method = data.payment_method
        if data.destination_account_id:
            bill.destination_account_id = data.destination_account_id
        if data.notes:
            bill.notes = (bill.notes or "") + f"\n[Baixa]: {data.notes}"

        db.commit()
        db.refresh(bill)
        return bill

    def cancel_bill(self, db: Session, tenant_id: int, bill_id: int) -> Optional[FinancialBill]:
        bill = (
            db.query(FinancialBill)
            .filter(
                FinancialBill.id == bill_id,
                FinancialBill.tenant_id == tenant_id,
            )
            .first()
        )
        if not bill:
            return None

        bill.status = "canceled"
        db.commit()
        db.refresh(bill)
        return bill

    def delete_bill(self, db: Session, tenant_id: int, bill_id: int) -> bool:
        bill = (
            db.query(FinancialBill)
            .filter(
                FinancialBill.id == bill_id,
                FinancialBill.tenant_id == tenant_id,
            )
            .first()
        )
        if not bill:
            return False

        # Desvincula possíveis parcelas filhas antes da exclusão
        db.query(FinancialBill).filter(
            FinancialBill.parent_bill_id == bill_id,
            FinancialBill.tenant_id == tenant_id,
        ).update({"parent_bill_id": None})

        db.delete(bill)
        db.commit()
        return True

    def get_all_for_export(
        self,
        db: Session,
        tenant_id: int,
        bill_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category_id: Optional[int] = None,
    ) -> List[FinancialBill]:
        today = date.today()
        query = (
            db.query(FinancialBill)
            .options(
                joinedload(FinancialBill.category),
                joinedload(FinancialBill.supplier),
                joinedload(FinancialBill.client),
            )
            .filter(FinancialBill.tenant_id == tenant_id)
        )

        if bill_type:
            query = query.filter(FinancialBill.bill_type == bill_type)
        if status:
            if status == "overdue":
                query = query.filter(
                    and_(
                        FinancialBill.status == "pending",
                        FinancialBill.due_date < today,
                    )
                )
            elif status == "pending":
                query = query.filter(
                    and_(
                        FinancialBill.status == "pending",
                        FinancialBill.due_date >= today,
                    )
                )
            else:
                query = query.filter(FinancialBill.status == status)

        if start_date:
            query = query.filter(FinancialBill.due_date >= start_date)
        if end_date:
            query = query.filter(FinancialBill.due_date <= end_date)
        if category_id:
            query = query.filter(FinancialBill.category_id == category_id)

        items = query.order_by(asc(FinancialBill.due_date)).all()
        for item in items:
            item.status = self._apply_overdue_status(item, today)

        return items
