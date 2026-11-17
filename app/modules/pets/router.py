import io
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    PetCreate,
    PetUpdate,
    PetResponse,
    PetPhotoResponse,
    ClientPetReportResponse,
)
from .service import PetService

router = APIRouter(prefix="/pets", tags=["Pets"], dependencies=[Depends(get_current_tenant)])


@router.post("/", response_model=PetResponse, dependencies=[Depends(require_active_subscription)])
def create_pet(
    data: PetCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_pet(db, tenant_id, data)


@router.get("/", response_model=list[PetResponse])
def list_pets(
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_pets(db, tenant_id)


@router.get("/client/{client_id}", response_model=list[PetResponse])
def list_pets_by_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_pets_by_client(db, tenant_id, client_id)


@router.get("/reports/clients-pets", response_model=ClientPetReportResponse)
def get_clients_pets_report(
    request: Request,
    is_active: bool | None = Query(None, description="Filtrar por status do pet"),
    search: str | None = Query(None, description="Busca por nome, cliente, telefone ou raça"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_clients_pets_report(
        db=db,
        tenant_id=tenant_id,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/reports/clients-pets/export")
def export_clients_pets_report(
    request: Request,
    is_active: bool | None = Query(None, description="Filtrar por status do pet"),
    search: str | None = Query(None, description="Busca por nome, cliente, telefone ou raça"),
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    excel_bytes = service.export_clients_pets_excel(
        db=db,
        tenant_id=tenant_id,
        is_active=is_active,
        search=search,
    )
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio_clientes_pets.xlsx"'
        },
    )


@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_pet(db, tenant_id, pet_id)


@router.patch("/{pet_id}", response_model=PetResponse, dependencies=[Depends(require_active_subscription)])
def update_pet(
    pet_id: int,
    data: PetUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_pet(db, tenant_id, pet_id, data)


@router.delete("/{pet_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_pet(
    pet_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_pet(db, tenant_id, pet_id)


@router.post("/{pet_id}/photos", response_model=PetPhotoResponse, dependencies=[Depends(require_active_subscription)])
async def add_pet_photo(
    pet_id: int,
    request: Request,
    file: UploadFile = File(...),
    is_profile: bool = Form(False),
    category: str = Form("general"),
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    file_content = await file.read()
    return service.add_pet_photo(
        db=db,
        tenant_id=tenant_id,
        pet_id=pet_id,
        file_content=file_content,
        filename=file.filename,
        content_type=file.content_type,
        is_profile=is_profile,
        category=category,
    )


@router.delete("/{pet_id}/photos/{photo_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_pet_photo(
    pet_id: int,
    photo_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_pet_photo(db, tenant_id, pet_id, photo_id)


@router.patch("/{pet_id}/photos/{photo_id}/set-profile", response_model=PetPhotoResponse, dependencies=[Depends(require_active_subscription)])
def set_profile_photo(
    pet_id: int,
    photo_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = PetService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.set_profile_photo(db, tenant_id, pet_id, photo_id)

