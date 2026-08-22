from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import DashboardStartupResponse

from app.modules.appointments.service import AppointmentService
from app.modules.client_packages.service import ClientPackageService
from app.modules.packages.service import PackageService
from app.modules.waiting_list.service import WaitingListService
from app.modules.waiting_list.models import WaitingListStatus

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(get_current_tenant)])

@router.get("/startup", response_model=DashboardStartupResponse)
def get_dashboard_startup(
    request: Request,
    target_date: date,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    tenant_id = request.state.tenant_user.tenant_id
    
    appointments = AppointmentService().list_by_day(db, tenant_id, target_date)
    highlighted = AppointmentService().list_highlighted_days(db, tenant_id, start_date, end_date)
    
    invoices_res = AppointmentService().list_open_invoices(db, tenant_id, limit=15)
    unpaid_res = ClientPackageService().list_unpaid_packages(db, tenant_id, limit=15)
    
    packages = PackageService().list_packages(db, tenant_id)
    waiting_list = WaitingListService().get_all(db, tenant_id, status=WaitingListStatus.PENDING)
    
    return DashboardStartupResponse(
        appointments_today=appointments,
        highlighted_days=highlighted,
        open_invoices=invoices_res,
        unpaid_packages=unpaid_res,
        packages_catalog=packages,
        waiting_list_pending=waiting_list
    )

