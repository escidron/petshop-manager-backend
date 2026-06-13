import uuid
from sqlalchemy.orm import Session

from .models import Employee
from .schemas import EmployeeCreate, EmployeeUpdate


class EmployeeRepository:
    def create(self, db: Session, tenant_id: int, data: EmployeeCreate) -> Employee:
        employee = Employee(
            tenant_id=tenant_id, 
            schedule_token=uuid.uuid4().hex, 
            **data.model_dump()
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        return employee

    def get_by_id(self, db: Session, tenant_id: int, employee_id: int) -> Employee | None:
        employee = (
            db.query(Employee)
            .filter(Employee.id == employee_id, Employee.tenant_id == tenant_id)
            .first()
        )
        if employee and not employee.schedule_token:
            employee.schedule_token = uuid.uuid4().hex
            db.commit()
            db.refresh(employee)
        return employee

    def list(self, db: Session, tenant_id: int) -> list[Employee]:
        employees = (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant_id)
            .order_by(Employee.name)
            .all()
        )
        updated = False
        for e in employees:
            if not e.schedule_token:
                e.schedule_token = uuid.uuid4().hex
                updated = True
        if updated:
            db.commit()
            for e in employees:
                try:
                    db.refresh(e)
                except Exception:
                    pass
        return employees

    def update(self, db: Session, employee: Employee, data: EmployeeUpdate) -> Employee:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(employee, field, value)
        db.commit()
        db.refresh(employee)
        return employee

    def delete(self, db: Session, employee: Employee) -> None:
        db.delete(employee)
        db.commit()
