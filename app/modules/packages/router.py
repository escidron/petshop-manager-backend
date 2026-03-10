from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import Package, PackageCreate, PackageUpdate
from .service import PackageService

router = APIRouter(prefix="/packages", tags=["Pacotes"], dependencies=[Depends(get_current_tenant)])

@router.post("/", response_model=Package)
def create_package(data: PackageCreate, request: Request, db: Session = Depends(get_db)):
    service = PackageService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_package(db, tenant_id, data)

@router.get("/", response_model=list[Package])
def list_packages(request: Request, db: Session = Depends(get_db)):
    service = PackageService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_packages(db, tenant_id)

@router.get("/{package_id}", response_model=Package)
def get_package(package_id: int, request: Request, db: Session = Depends(get_db)):
    service = PackageService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_package(db, tenant_id, package_id)

@router.patch("/{package_id}", response_model=Package)
def update_package(package_id: int, data: PackageUpdate, request: Request, db: Session = Depends(get_db)):
    service = PackageService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_package(db, tenant_id, package_id, data)

@router.delete("/{package_id}", status_code=204)
def delete_package(package_id: int, request: Request, db: Session = Depends(get_db)):
    service = PackageService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_package(db, tenant_id, package_id)
