from pydantic import BaseModel
from datetime import date
from app.modules.appointments.schemas import AppointmentResponse, PaginatedAppointmentsResponse
from app.modules.client_packages.schemas import PaginatedClientPackagesResponse
from app.modules.packages.schemas import Package
from app.modules.waiting_list.schemas import WaitingListEntryResponse

class DashboardStartupResponse(BaseModel):
    appointments_today: list[AppointmentResponse]
    highlighted_days: list[date]
    open_invoices: PaginatedAppointmentsResponse
    unpaid_packages: PaginatedClientPackagesResponse
    packages_catalog: list[Package]
    waiting_list_pending: list[WaitingListEntryResponse]

