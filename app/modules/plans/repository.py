from sqlalchemy.orm import Session

from app.modules.plans.models import Plan


class PlanRepository:
    def get_by_code(self, db: Session, code: str) -> Plan | None:
        return db.query(Plan).filter(
            Plan.code == code,
            Plan.is_active
        ).first()