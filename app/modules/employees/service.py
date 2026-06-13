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

    def regenerate_token(self, db: Session, tenant_id: int, employee_id: int):
        import uuid
        employee = self.get_employee(db, tenant_id, employee_id)
        employee.schedule_token = uuid.uuid4().hex
        db.commit()
        db.refresh(employee)
        return employee

    def get_appointments_by_token(self, db: Session, token: str):
        from .models import Employee
        from app.modules.appointments.models import Appointment, AppointmentItem, AppointmentItemService

        employee = db.query(Employee).filter(Employee.schedule_token == token, Employee.is_active == True).first()
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agenda não encontrada ou funcionário inativo.")

        db_appointments = (
            db.query(Appointment)
            .join(AppointmentItem)
            .join(AppointmentItemService, AppointmentItemService.appointment_item_id == AppointmentItem.id)
            .filter(
                AppointmentItemService.employee_id == employee.id,
                Appointment.status != "canceled"
            )
            .order_by(Appointment.scheduled_at.asc())
            .all()
        )

        appointments_list = []
        for appt in db_appointments:
            items_list = []
            for item in appt.items:
                assigned_item_services = db.query(AppointmentItemService).filter(
                    AppointmentItemService.appointment_item_id == item.id,
                    AppointmentItemService.employee_id == employee.id
                ).all()
                assigned_service_ids = {ais.service_id for ais in assigned_item_services}

                if not assigned_service_ids:
                    continue

                services_list = []
                for svc in item.services:
                    if svc.id in assigned_service_ids:
                        services_list.append({
                            "id": svc.id,
                            "name": svc.name,
                            "duration_minutes": getattr(svc, "duration_minutes", None)
                        })

                if services_list:
                    items_list.append({
                        "id": item.id,
                        "pet": {
                            "id": item.pet.id,
                            "name": item.pet.name,
                            "species": item.pet.species,
                            "breed": item.pet.breed
                        },
                        "services": services_list
                    })

            if items_list:
                appointments_list.append({
                    "id": appt.id,
                    "scheduled_at": appt.scheduled_at,
                    "status": appt.status.value if hasattr(appt.status, "value") else str(appt.status),
                    "notes": appt.notes,
                    "client_name": appt.client.name,
                    "client_phone": appt.client.phone,
                    "items": items_list
                })

        from app.modules.tenants.models import Tenant
        tenant = db.query(Tenant).filter(Tenant.id == employee.tenant_id).first()
        petshop_name = tenant.name if tenant else "Petshop"

        return {
            "employee_name": employee.name,
            "employee_role": employee.role.value if hasattr(employee.role, "value") else str(employee.role),
            "petshop_name": petshop_name,
            "appointments": appointments_list
        }

    def delete_employee(self, db: Session, tenant_id: int, employee_id: int):
        employee = self.get_employee(db, tenant_id, employee_id)
        self.repository.delete(db, employee)
