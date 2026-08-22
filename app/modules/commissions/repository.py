from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from .models import CommissionRule, CommissionEntry
from .schemas import CommissionRuleCreate, CommissionRuleUpdate
from app.modules.tenant_services.models import Service


def _specificity(rule: CommissionRule) -> int:
    """employee+services=3, só employee=2, só services=1, global=0"""
    score = 0
    if rule.employee_id is not None:
        score += 2
    if rule.services:
        score += 1
    return score


class CommissionRuleRepository:
    def _load_services(self, db: Session, service_ids: list[int]) -> list[Service]:
        if not service_ids:
            return []
        return db.query(Service).filter(Service.id.in_(service_ids)).all()

    def create(self, db: Session, tenant_id: int, data: CommissionRuleCreate) -> CommissionRule:
        rule = CommissionRule(
            tenant_id=tenant_id,
            **data.model_dump(exclude={"service_ids"}),
        )
        db.add(rule)
        db.flush()
        rule.services = self._load_services(db, data.service_ids)
        db.commit()
        db.refresh(rule)
        return rule

    def get_by_id(self, db: Session, tenant_id: int, rule_id: int) -> CommissionRule | None:
        return (
            db.query(CommissionRule)
            .options(
                joinedload(CommissionRule.employee),
                joinedload(CommissionRule.services),
            )
            .filter(CommissionRule.id == rule_id, CommissionRule.tenant_id == tenant_id)
            .first()
        )

    def list(self, db: Session, tenant_id: int) -> list[CommissionRule]:
        rules = (
            db.query(CommissionRule)
            .options(
                joinedload(CommissionRule.employee),
                joinedload(CommissionRule.services),
            )
            .filter(CommissionRule.tenant_id == tenant_id)
            .order_by(CommissionRule.name)
            .all()
        )
        return sorted(rules, key=lambda r: -_specificity(r))


    def update(self, db: Session, rule: CommissionRule, data: CommissionRuleUpdate) -> CommissionRule:
        for field, value in data.model_dump(exclude_unset=True, exclude={"service_ids"}).items():
            setattr(rule, field, value)

        if "service_ids" in data.model_fields_set:
            rule.services = self._load_services(db, data.service_ids or [])

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
        candidates = (
            db.query(CommissionRule)
            .options(joinedload(CommissionRule.services))
            .filter(
                CommissionRule.tenant_id == tenant_id,
                CommissionRule.is_active == True,
                or_(CommissionRule.valid_from == None, CommissionRule.valid_from <= ref_date),
                or_(CommissionRule.valid_until == None, CommissionRule.valid_until >= ref_date),
            )
            .all()
        )

        matching = [
            r for r in candidates
            if (r.employee_id is None or r.employee_id == employee_id)
            and (
                not r.services
                or (service_id is not None and service_id in {s.id for s in r.services})
            )
            and (r.applies_to == "both" or r.applies_to == item_type)
        ]

        if not matching:
            return None

        return max(matching, key=lambda r: (_specificity(r), -r.id))


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
