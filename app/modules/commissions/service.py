from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import CommissionRule, CommissionEntry
from .repository import CommissionRuleRepository, CommissionEntryRepository
from .schemas import (
    CommissionRuleCreate,
    CommissionRuleUpdate,
    CommissionPayRequest,
)


class CommissionService:
    def __init__(self):
        self.rule_repo = CommissionRuleRepository()
        self.entry_repo = CommissionEntryRepository()

    # ── Rules ────────────────────────────────────────────────────────────────

    def create_rule(self, db: Session, tenant_id: int, data: CommissionRuleCreate):
        return self.rule_repo.create(db, tenant_id, data)

    def get_rule(self, db: Session, tenant_id: int, rule_id: int):
        rule = self.rule_repo.get_by_id(db, tenant_id, rule_id)
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada.")
        return rule

    def list_rules(self, db: Session, tenant_id: int):
        return self.rule_repo.list(db, tenant_id)

    def update_rule(self, db: Session, tenant_id: int, rule_id: int, data: CommissionRuleUpdate):
        rule = self.get_rule(db, tenant_id, rule_id)
        return self.rule_repo.update(db, rule, data)

    def delete_rule(self, db: Session, tenant_id: int, rule_id: int):
        rule = self.get_rule(db, tenant_id, rule_id)
        self.rule_repo.delete(db, rule)

    # ── Entry generation ──────────────────────────────────────────────────────

    def generate_entry(
        self,
        db: Session,
        tenant_id: int,
        employee_id: int,
        service_id: int | None,
        item_type: str,
        subtotal: Decimal,
        ref_date: date,
        sale_id: int | None = None,
        sale_item_id: int | None = None,
        appointment_item_id: int | None = None,
    ) -> CommissionEntry | None:
        rule = self.rule_repo.resolve(
            db, tenant_id, employee_id, service_id, item_type, ref_date
        )
        if not rule:
            return None

        if rule.commission_type == "percentage":
            amount = subtotal * rule.value / Decimal("100")
        else:
            amount = rule.value

        entry = CommissionEntry(
            tenant_id=tenant_id,
            sale_id=sale_id,
            sale_item_id=sale_item_id,
            appointment_item_id=appointment_item_id,
            employee_id=employee_id,
            rule_id=rule.id,
            commission_type=rule.commission_type,
            rate=rule.value,
            base_amount=subtotal,
            commission_amount=amount.quantize(Decimal("0.01")),
            status="pending",
        )
        self.entry_repo.create(db, entry)
        return entry

    def generate_retroactive(
        self,
        db: Session,
        tenant_id: int,
        employee_id: int,
        service_id: int | None,
        item_type: str,
        subtotal: Decimal,
        ref_date: date,
        sale_id: int | None = None,
        sale_item_id: int | None = None,
        appointment_item_id: int | None = None,
    ) -> CommissionEntry | None:
        if self.entry_repo.exists_for_sale_item(db, sale_item_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Comissão já foi calculada para este item.",
            )
        entry = self.generate_entry(
            db, tenant_id, employee_id, service_id, item_type, subtotal, ref_date,
            sale_id=sale_id, sale_item_id=sale_item_id
        )
        db.commit()
        return entry

    # ── Report & payment ─────────────────────────────────────────────────────

    def list_entries(
        self,
        db: Session,
        tenant_id: int,
        employee_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ):
        return self.entry_repo.list_by_tenant(db, tenant_id, employee_id, status, from_date, to_date)

    def pay_entries(self, db: Session, tenant_id: int, data: CommissionPayRequest):
        entries = self.entry_repo.get_by_ids(db, tenant_id, data.entry_ids)
        if not entries:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhuma entrada encontrada.")

        for entry in entries:
            if entry.employee_id != data.employee_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Entrada {entry.id} não pertence ao funcionário informado.",
                )
            if entry.status == "paid":
                continue
            entry.status = "paid"
            entry.paid_at = datetime.now(timezone.utc)
            if data.notes:
                entry.notes = data.notes

        db.commit()
        return entries
