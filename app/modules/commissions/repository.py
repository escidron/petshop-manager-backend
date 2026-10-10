from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from .models import CommissionRule, CommissionEntry
from .schemas import CommissionRuleCreate, CommissionRuleUpdate
from app.modules.tenant_services.models import Service
from app.modules.employees.models import Employee


def _specificity(rule: CommissionRule) -> int:
    """
    employee + services/products = 5
    employee only = 4
    role + services/products = 3
    role only = 2
    services/products only = 1
    global = 0
    """
    score = 0
    if rule.employees:
        score += 4
    elif rule.roles:
        score += 2
    if rule.services or (getattr(rule, "product_ids", None) and rule.product_ids):
        score += 1
    return score


class CommissionRuleRepository:
    def _load_employees(self, db: Session, employee_ids: list[int]) -> list[Employee]:
        if not employee_ids:
            return []
        return db.query(Employee).filter(Employee.id.in_(employee_ids)).all()

    def _load_services(self, db: Session, service_ids: list[int]) -> list[Service]:
        if not service_ids:
            return []
        return db.query(Service).filter(Service.id.in_(service_ids)).all()

    def create(self, db: Session, tenant_id: int, data: CommissionRuleCreate) -> CommissionRule:
        rule = CommissionRule(
            tenant_id=tenant_id,
            **data.model_dump(exclude={"service_ids", "employee_ids", "employee_id"}),
        )
        db.add(rule)
        db.flush()
        rule.services = self._load_services(db, data.service_ids)
        emp_ids = data.employee_ids or ([data.employee_id] if data.employee_id else [])
        rule.employees = self._load_employees(db, emp_ids)
        db.commit()
        db.refresh(rule)
        return rule

    def get_by_id(self, db: Session, tenant_id: int, rule_id: int) -> CommissionRule | None:
        return (
            db.query(CommissionRule)
            .options(
                joinedload(CommissionRule.employees),
                joinedload(CommissionRule.services),
            )
            .filter(CommissionRule.id == rule_id, CommissionRule.tenant_id == tenant_id)
            .first()
        )

    def list(self, db: Session, tenant_id: int) -> list[CommissionRule]:
        rules = (
            db.query(CommissionRule)
            .options(
                joinedload(CommissionRule.employees),
                joinedload(CommissionRule.services),
            )
            .filter(CommissionRule.tenant_id == tenant_id)
            .order_by(CommissionRule.name)
            .all()
        )
        return sorted(rules, key=lambda r: -_specificity(r))


    def update(self, db: Session, rule: CommissionRule, data: CommissionRuleUpdate) -> CommissionRule:
        for field, value in data.model_dump(exclude_unset=True, exclude={"service_ids", "employee_ids", "employee_id"}).items():
            setattr(rule, field, value)

        if "employee_ids" in data.model_fields_set:
            rule.employees = self._load_employees(db, data.employee_ids or [])
        elif "employee_id" in data.model_fields_set:
            emp_ids = [data.employee_id] if data.employee_id else []
            rule.employees = self._load_employees(db, emp_ids)

        if "service_ids" in data.model_fields_set:
            rule.services = self._load_services(db, data.service_ids or [])

        if "product_ids" in data.model_fields_set:
            rule.product_ids = data.product_ids or []

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
        product_id: int | None = None,
    ) -> CommissionRule | None:
        employee = (
            db.query(Employee)
            .filter(Employee.id == employee_id, Employee.tenant_id == tenant_id)
            .first()
        )
        if not employee:
            return None

        emp_role = (
            employee.role.value if hasattr(employee.role, "value") else str(employee.role or "")
        ).strip().lower()

        candidates = (
            db.query(CommissionRule)
            .options(
                joinedload(CommissionRule.employees),
                joinedload(CommissionRule.services),
            )
            .filter(
                CommissionRule.tenant_id == tenant_id,
                CommissionRule.is_active == True,
                or_(CommissionRule.valid_from == None, CommissionRule.valid_from <= ref_date),
                or_(CommissionRule.valid_until == None, CommissionRule.valid_until >= ref_date),
            )
            .all()
        )

        matching = []
        for r in candidates:
            # 1. Se a regra tiver funcionários específicos, o funcionário precisa estar nela
            # 2. Senão, se a regra tiver cargos (roles), o cargo do funcionário precisa estar em r.roles
            # 3. Senão (sem funcionários e sem cargos), a regra é global e atende a todos
            rule_roles = [str(x).strip().lower() for x in (r.roles or []) if str(x).strip()]
            if r.employees:
                if employee_id not in {e.id for e in r.employees}:
                    continue
            elif rule_roles:
                if emp_role not in rule_roles:
                    continue

            # Validação de serviço ou produto conforme o item da venda
            if item_type == "service":
                if r.services:
                    if service_id is None or service_id not in {s.id for s in r.services}:
                        continue
            elif item_type == "product":
                if getattr(r, "product_ids", None):
                    if product_id is None or product_id not in (r.product_ids or []):
                        continue

            # Validação de abrangência (service / product / both)
            if r.applies_to != "both" and r.applies_to != item_type:
                continue

            matching.append(r)

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
        if from_date or to_date:
            from app.utils.timezone import get_date_range_bounds_brazil
            start_dt, end_dt = get_date_range_bounds_brazil(from_date, to_date)
            if start_dt:
                q = q.filter(CommissionEntry.created_at >= start_dt)
            if end_dt:
                q = q.filter(CommissionEntry.created_at <= end_dt)
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
