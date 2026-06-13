from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import EmployeeCreate, EmployeeUpdate, EmployeeResponse, PublicFreelancerScheduleResponse
from .service import EmployeeService

router = APIRouter(prefix="/employees", tags=["Employees"], dependencies=[Depends(get_current_tenant)])
public_router = APIRouter(prefix="/public/employees", tags=["Public Employees"])


@public_router.get("/schedule/{token}", response_model=PublicFreelancerScheduleResponse)
def get_public_schedule(token: str, db: Session = Depends(get_db)):
    service = EmployeeService()
    return service.get_appointments_by_token(db, token)



@router.post("/", response_model=EmployeeResponse, dependencies=[Depends(require_active_subscription)])
def create_employee(data: EmployeeCreate, request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_employee(db, tenant_id, data)


@router.get("/", response_model=list[EmployeeResponse])
def list_employees(request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_employees(db, tenant_id)


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: int, request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_employee(db, tenant_id, employee_id)


@router.patch("/{employee_id}", response_model=EmployeeResponse, dependencies=[Depends(require_active_subscription)])
def update_employee(employee_id: int, data: EmployeeUpdate, request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_employee(db, tenant_id, employee_id, data)


@router.post("/{employee_id}/regenerate-token", response_model=EmployeeResponse, dependencies=[Depends(require_active_subscription)])
def regenerate_token(employee_id: int, request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.regenerate_token(db, tenant_id, employee_id)


@router.delete("/{employee_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_employee(employee_id: int, request: Request, db: Session = Depends(get_db)):
    service = EmployeeService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_employee(db, tenant_id, employee_id)
