from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .models import CommissionRule, CommissionEntry
from .schemas import CommissionRuleCreate, CommissionRuleUpdate


class CommissionRuleRepository:
    def create(self, db: Session, tenant_id: int, data: CommissionRuleCreate) -> CommissionRule:
        rule = CommissionRule(tenant_id=tenant_id, **data.model_dump())
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def get_by_id(self, db: Session, tenant_id: int, rule_id: int) -> CommissionRule | None:
        return (
            db.query(CommissionRule)
            .filter(CommissionRule.id == rule_id, CommissionRule.tenant_id == tenant_id)
            .first()
        )

    def list(self, db: Session, tenant_id: int) -> list[CommissionRule]:
        return (
            db.query(CommissionRule)
            .filter(CommissionRule.tenant_id == tenant_id)
            .order_by(CommissionRule.priority, CommissionRule.name)
            .all()
        )

    def update(self, db: Session, rule: CommissionRule, data: CommissionRuleUpdate) -> CommissionRule:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        db.commit()
        db.refresh(rule)
        return rule

    def delete(self, db: Session, rule: CommissionRule) -> None:
        db.delete(rule)
        db.commit()

    def resolve(
        self,
        db: Session,
        tenant_id: int,
        employee_id: int,
        service_id: int | None,
        item_type: str,
        ref_date: date,
    ) -> CommissionRule | None:
        rules = (
            db.query(CommissionRule)
            .filter(
                CommissionRule.tenant_id == tenant_id,
                CommissionRule.is_active == True,
                or_(CommissionRule.valid_from == None, CommissionRule.valid_from <= ref_date),
                or_(CommissionRule.valid_until == None, CommissionRule.valid_until >= ref_date),
            )
            .order_by(CommissionRule.priority.asc())
            .all()
        )

        for rule in rules:
            if rule.employee_id and rule.employee_id != employee_id:
                continue
            if rule.service_id and rule.service_id != service_id:
                continue
            if rule.applies_to != "both" and rule.applies_to != item_type:
                continue
            return rule

        return None


class CommissionEntryRepository:
    def create(self, db: Session, entry: CommissionEntry) -> CommissionEntry:
        db.add(entry)
        return entry

    def list_by_tenant(
        self,
        db: Session,
        tenant_id: int,
        employee_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[CommissionEntry]:
        q = db.query(CommissionEntry).filter(CommissionEntry.tenant_id == tenant_id)
        if employee_id:
            q = q.filter(CommissionEntry.employee_id == employee_id)
        if status:
            q = q.filter(CommissionEntry.status == status)
        if from_date:
            from datetime import datetime, time
            q = q.filter(CommissionEntry.created_at >= datetime.combine(from_date, time.min))
        if to_date:
            from datetime import datetime, time
            q = q.filter(CommissionEntry.created_at <= datetime.combine(to_date, time.max))
        return q.order_by(CommissionEntry.created_at.desc()).all()

    def get_by_ids(self, db: Session, tenant_id: int, entry_ids: list[int]) -> list[CommissionEntry]:
        return (
            db.query(CommissionEntry)
            .filter(
                CommissionEntry.tenant_id == tenant_id,
                CommissionEntry.id.in_(entry_ids),
            )
            .all()
        )

    def exists_for_sale_item(self, db: Session, sale_item_id: int) -> bool:
        return (
            db.query(CommissionEntry)
            .filter(CommissionEntry.sale_item_id == sale_item_id)
            .first()
        ) is not None
