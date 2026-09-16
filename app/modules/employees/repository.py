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

        if data.admission_date or data.resignation_date:
            try:
                from app.modules.financial.models import EmployeePayrollProfile
                profile = (
                    db.query(EmployeePayrollProfile)
                    .filter(
                        EmployeePayrollProfile.tenant_id == tenant_id,
                        EmployeePayrollProfile.employee_id == employee.id,
                    )
                    .first()
                )
                if not profile:
                    profile = EmployeePayrollProfile(
                        tenant_id=tenant_id,
                        employee_id=employee.id,
                        admission_date=data.admission_date,
                        resignation_date=data.resignation_date,
                    )
                    db.add(profile)
                else:
                    profile.admission_date = data.admission_date
                    profile.resignation_date = data.resignation_date
                db.commit()
            except Exception:
                pass

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
        update_dict = data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(employee, field, value)
        db.commit()
        db.refresh(employee)

        if "admission_date" in update_dict or "resignation_date" in update_dict:
            try:
                from app.modules.financial.models import EmployeePayrollProfile
                profile = (
                    db.query(EmployeePayrollProfile)
                    .filter(
                        EmployeePayrollProfile.tenant_id == employee.tenant_id,
                        EmployeePayrollProfile.employee_id == employee.id,
                    )
                    .first()
                )
                if not profile:
                    profile = EmployeePayrollProfile(
                        tenant_id=employee.tenant_id,
                        employee_id=employee.id,
                        admission_date=update_dict.get("admission_date", employee.admission_date),
                        resignation_date=update_dict.get("resignation_date", employee.resignation_date),
                    )
                    db.add(profile)
                else:
                    if "admission_date" in update_dict:
                        profile.admission_date = update_dict["admission_date"]
                    if "resignation_date" in update_dict:
                        profile.resignation_date = update_dict["resignation_date"]
                db.commit()
            except Exception:
                pass

        return employee

    def delete(self, db: Session, employee: Employee) -> None:
        db.delete(employee)
        db.commit()
