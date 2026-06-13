import sys
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

# Setup path to import app modules
sys.path.append(".")

from app.modules.models_loader import load_all_models
load_all_models()

from app.config.database import SessionLocal
from app.modules.employees.models import Employee, EmployeeRole
from app.modules.employees.service import EmployeeService
from app.modules.tenants.models import Tenant, TenantType
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.modules.appointments.models import Appointment, AppointmentItem, AppointmentItemService, AppointmentStatus

def test_freelancer_schedule_flow():
    db = SessionLocal()
    try:
        print("=== TEST: Freelancer Schedule Flow ===")
        
        # 1. Create a tenant type and tenant if not exist
        tenant_type = db.query(TenantType).filter(TenantType.code == "test_type").first()
        if not tenant_type:
            tenant_type = TenantType(code="test_type", name="Test Type")
            db.add(tenant_type)
            db.commit()
            db.refresh(tenant_type)

        tenant = Tenant(name="Test Tenant Freelancer", type_id=tenant_type.id, phone="11999999999", is_active=True)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        print(f"Tenant created: ID={tenant.id}")

        # 2. Create an employee (should automatically generate schedule_token)
        service = EmployeeService()
        from app.modules.employees.schemas import EmployeeCreate
        emp_data = EmployeeCreate(name="Freelancer João", role="groomer", phone="11999999999", email="joao@example.com")
        employee = service.create_employee(db, tenant.id, emp_data)
        print(f"Employee created: ID={employee.id}, schedule_token={employee.schedule_token}")
        assert employee.schedule_token is not None, "schedule_token was not generated!"

        # 3. Create a client and pet
        client = Client(tenant_id=tenant.id, name="Maria Tutor", phone="11888888888")
        db.add(client)
        db.commit()
        db.refresh(client)
        print(f"Client created: ID={client.id}")

        pet = Pet(tenant_id=tenant.id, client_id=client.id, name="Rex", species="Cachorro")
        db.add(pet)
        db.commit()
        db.refresh(pet)
        print(f"Pet created: ID={pet.id}")

        # 4. Create a service
        service_item = Service(tenant_id=tenant.id, name="Banho Completo", price_cents=5000, duration_minutes=60)
        db.add(service_item)
        db.commit()
        db.refresh(service_item)
        print(f"Service created: ID={service_item.id}")

        # 5. Create an Appointment (Pending) and assign the employee to it
        # We simulate the ORM relationship creation
        appt = Appointment(
            tenant_id=tenant.id,
            client_id=client.id,
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            status=AppointmentStatus.PENDING,
            notes="Rex está agitado"
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        print(f"Appointment created: ID={appt.id}")

        appt_item = AppointmentItem(
            appointment_id=appt.id,
            pet_id=pet.id
        )
        db.add(appt_item)
        db.commit()
        db.refresh(appt_item)
        print(f"AppointmentItem created: ID={appt_item.id}")

        # Link service to appointment item
        # In SQL Alchemy, we append to the secondary relationship:
        appt_item.services.append(service_item)
        db.commit()

        # Link employee to the service (updating the row automatically created by services.append)
        item_svc = db.query(AppointmentItemService).filter(
            AppointmentItemService.appointment_item_id == appt_item.id,
            AppointmentItemService.service_id == service_item.id
        ).first()
        assert item_svc is not None, "AppointmentItemService link row was not auto-created!"
        item_svc.employee_id = employee.id
        db.commit()
        print("Employee assigned to service successfully.")

        # 6. Retrieve public schedule using token
        schedule = service.get_appointments_by_token(db, employee.schedule_token)
        print(f"Schedule retrieved: {schedule}")
        assert schedule["employee_name"] == "Freelancer João"
        assert len(schedule["appointments"]) == 1
        appt_retrieved = schedule["appointments"][0]
        assert appt_retrieved["client_name"] == "Maria Tutor"
        assert appt_retrieved["items"][0]["pet"]["name"] == "Rex"
        assert appt_retrieved["items"][0]["services"][0]["name"] == "Banho Completo"
        
        # 7. Test token regeneration
        old_token = employee.schedule_token
        service.regenerate_token(db, tenant.id, employee.id)
        db.refresh(employee)
        new_token = employee.schedule_token
        print(f"Token regenerated: Old={old_token}, New={new_token}")
        assert old_token != new_token, "Token was not regenerated!"
        
        print("=== TEST SUCCESSFUL ===")
    finally:
        # Cleanup
        db.rollback()
        db.close()

if __name__ == "__main__":
    test_freelancer_schedule_flow()
