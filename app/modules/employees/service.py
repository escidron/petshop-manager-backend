from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .repository import EmployeeRepository
from .schemas import EmployeeCreate, EmployeeUpdate


class EmployeeService:
    def __init__(self):
        self.repository = EmployeeRepository()

    def create_employee(self, db: Session, tenant_id: int, data: EmployeeCreate):
        return self.repository.create(db, tenant_id, data)

    def get_employee(self, db: Session, tenant_id: int, employee_id: int):
        employee = self.repository.get_by_id(db, tenant_id, employee_id)
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funcionário não encontrado.")
        return employee

    def list_employees(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def update_employee(self, db: Session, tenant_id: int, employee_id: int, data: EmployeeUpdate):
        employee = self.get_employee(db, tenant_id, employee_id)
        return self.repository.update(db, employee, data)

    def delete_employee(self, db: Session, tenant_id: int, employee_id: int):
        employee = self.get_employee(db, tenant_id, employee_id)
        self.repository.delete(db, employee)
