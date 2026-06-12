from datetime import datetime, timedelta, timezone
from app.config.database import SessionLocal

# Import all models to resolve mapper relationships
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.modules.appointments.models import Appointment, AppointmentItem, AppointmentItemService
from app.modules.packages.models import Package, PackageItem
from app.modules.sales.models import Sale, SaleItem
from app.modules.plans.models import Plan
from app.modules.subscriptions.models import Subscription
from app.modules.users.models import User, TenantUser
from app.modules.tenants.models import Tenant
from app.modules.client_packages.models import ClientPackage, ClientPackageCredit
from app.modules.employees.models import Employee
from app.modules.commissions.models import CommissionRule, CommissionEntry

def seed_perf():
    db = SessionLocal()
    try:
        tenant_id = 140
        client_id = 327
        pet_id = 181
        service_id = 240
        
        # Populate for May 2026
        # Let's say 1500 appointments total, spread across 31 days in May
        # That's about 50 appointments per day
        start_date = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
        
        print(f"Creating 1500 appointments for May 2026 (tenant_id={tenant_id}, client_id={client_id}, pet_id={pet_id})...")
        
        created = 0
        for i in range(1500):
            day_offset = i % 31
            hour_offset = (i // 31) % 10  # 8am to 5pm
            scheduled_at = start_date + timedelta(days=day_offset, hours=hour_offset)
            
            appt = Appointment(
                tenant_id=tenant_id,
                client_id=client_id,
                scheduled_at=scheduled_at,
                status="pending"
            )
            db.add(appt)
            db.flush()
            
            appt_item = AppointmentItem(
                appointment_id=appt.id,
                pet_id=pet_id
            )
            db.add(appt_item)
            db.flush()
            
            item_service = AppointmentItemService(
                appointment_item_id=appt_item.id,
                service_id=service_id
            )
            db.add(item_service)
            
            created += 1
            if created % 300 == 0:
                print(f"  {created}/1500 created...")
                
        db.commit()
        print("Done!")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_perf()
