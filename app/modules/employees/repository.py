from sqlalchemy.orm import Session

from .models import Employee
from .schemas import EmployeeCreate, EmployeeUpdate


class EmployeeRepository:
    def create(self, db: Session, tenant_id: int, data: EmployeeCreate) -> Employee:
        employee = Employee(tenant_id=tenant_id, **data.model_dump())
        db.add(employee)
        db.commit()
        db.refresh(employee)
        return employee

    def get_by_id(self, db: Session, tenant_id: int, employee_id: int) -> Employee | None:
        return (
            db.query(Employee)
            .filter(Employee.id == employee_id, Employee.tenant_id == tenant_id)
            .first()
        )

    def list(self, db: Session, tenant_id: int) -> list[Employee]:
        return (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant_id)
            .order_by(Employee.name)
            .all()
        )

    def update(self, db: Session, employee: Employee, data: EmployeeUpdate) -> Employee:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(employee, field, value)
        db.commit()
        db.refresh(employee)
        return employee

    def delete(self, db: Session, employee: Employee) -> None:
        db.delete(employee)
        db.commit()
