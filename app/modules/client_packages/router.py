from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import ClientPackageResponse, ClientPackageSellRequest, ClientPackageCreditResponse, ClientPackageUsageResponse
from .service import ClientPackageService

router = APIRouter(
    prefix="/client-packages",
    tags=["Pacotes de Clientes"],
    dependencies=[Depends(get_current_tenant)],
)


@router.post("/", response_model=ClientPackageResponse, status_code=201, dependencies=[Depends(require_active_subscription)])
def sell_package(
    data: ClientPackageSellRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    from app.modules.pets.models import Pet
    pet = db.query(Pet).filter(Pet.id == data.pet_id, Pet.tenant_id == tenant_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet não encontrado")
    return svc.sell(db, tenant_id, pet.client_id, data)


@router.get("/unpaid", response_model=list[ClientPackageResponse])
def list_unpaid(
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    return svc.list_unpaid_packages(db, tenant_id)


@router.get("/pet/{pet_id}", response_model=list[ClientPackageResponse])
def list_by_pet(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    return svc.list_by_pet(db, tenant_id, pet_id)


@router.get("/client/{client_id}", response_model=list[ClientPackageResponse])
def list_by_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    return svc.list_by_client(db, tenant_id, client_id)


@router.delete("/{client_package_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def deactivate(
    client_package_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    svc.deactivate(db, tenant_id, client_package_id)


@router.post("/credits/{credit_id}/consume", response_model=ClientPackageCreditResponse)
def consume_credit(
    credit_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    return svc.consume_credit(db, tenant_id, credit_id)


@router.post("/credits/{credit_id}/revert", response_model=ClientPackageCreditResponse)
def revert_credit(
    credit_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    return svc.revert_credit(db, tenant_id, credit_id)


@router.get("/{client_package_id}/usages", response_model=list[ClientPackageUsageResponse])
def get_usages(
    client_package_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    svc = ClientPackageService()
    usages = svc.get_usages(db, tenant_id, client_package_id)
    
    response_usages = []
    for usage in usages:
        service_name = usage.credit.service_name if usage.credit else "Serviço"
        response_usages.append({
            "id": usage.id,
            "client_package_id": usage.client_package_id,
            "credit_id": usage.credit_id,
            "change_qty": usage.change_qty,
            "notes": usage.notes,
            "created_at": usage.created_at,
            "service_name": service_name
        })
    return response_usages
