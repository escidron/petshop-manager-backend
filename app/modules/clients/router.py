import asyncio
import io
from fastapi import APIRouter, BackgroundTasks, Depends, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription, require_owner
from .schemas import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientSummaryResponse,
)
from .service import ClientService
from .import_jobs import create_job, get_job

router = APIRouter(prefix="/clients", tags=["Clients"], dependencies=[Depends(get_current_tenant)])

@router.get("/export", dependencies=[Depends(require_owner)])
def export_clients(
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    excel_data = service.export_to_excel(db, tenant_id)
    return StreamingResponse(
        io.BytesIO(excel_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="backup_clientes.xlsx"'}
    )




@router.post("/", response_model=ClientResponse, dependencies=[Depends(require_active_subscription)])
def create_client(
    data: ClientCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_client(db, tenant_id, data)


@router.get("/", response_model=list[ClientSummaryResponse])
def list_clients(
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_clients(db, tenant_id)


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_client(db, tenant_id, client_id)


@router.patch("/{client_id}", response_model=ClientResponse, dependencies=[Depends(require_active_subscription)])
def update_client(
    client_id: int,
    data: ClientUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_client(db, tenant_id, client_id, data)


@router.delete("/{client_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_client(db, tenant_id, client_id)


@router.get("/import/template")
def get_import_template():
    service = ClientService()
    content = service.generate_import_template_excel()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_clientes_pets.xlsx"},
    )


@router.post("/import", dependencies=[Depends(require_active_subscription)])
async def import_clients(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Starts the bulk import as a background task and immediately returns a job_id.
    The client should poll GET /import/status/{job_id} to track progress.
    """
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    file_content = await file.read()

    job_id = create_job(tenant_id=tenant_id, job_type="clients")


    def _run_in_background():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                service.import_clients_from_excel_background(job_id, tenant_id, file_content)
            )
        finally:
            loop.close()

    background_tasks.add_task(_run_in_background)

    return {"job_id": job_id}


@router.get("/import/status/{job_id}")
def get_import_status(job_id: str):
    """
    Returns the current status/progress of a bulk import job.
    """
    job = get_job(job_id)
    if not job:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job não encontrado")
    return job


# ---------------------------------------------------------------------------
# Migration Wizard Endpoints (Assistente de Migração de Competidores)
# ---------------------------------------------------------------------------
@router.post("/migration/inspect", dependencies=[Depends(require_active_subscription)])
async def inspect_migration_files(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
):
    """
    Reads headers from 1 or 2 uploaded Excel files to let the frontend build the column mapper.
    """
    from app.modules.clients.migration_service import MigrationService
    m_service = MigrationService()

    content1 = await file1.read()
    headers1 = m_service.inspect_excel_headers(content1)

    headers2 = []
    if file2:
        content2 = await file2.read()
        headers2 = m_service.inspect_excel_headers(content2)

    return {
        "file1_headers": headers1,
        "file2_headers": headers2,
    }


@router.post("/migration/convert", dependencies=[Depends(require_active_subscription)])
async def convert_migration_files(
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    config: str = Form(...),  # JSON string with mapping instructions
):
    """
    Converts 1 or 2 competitor Excel files into a downloadable system-standard template Excel file.
    """
    import json
    from app.modules.clients.migration_service import MigrationService
    m_service = MigrationService()

    try:
        mapping_config = json.loads(config)
    except Exception:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuração de mapeamento inválida")

    content1 = await file1.read()
    content2 = await file2.read() if file2 else None

    is_two_files = mapping_config.get("mode") == "two_files" and content2 is not None

    if is_two_files:
        items = m_service.map_two_files(
            clients_file_content=content1,
            pets_file_content=content2,
            client_link_key=mapping_config.get("client_link_key", ""),
            pet_link_key=mapping_config.get("pet_link_key", ""),
            client_column_mapping=mapping_config.get("client_column_mapping", {}),
            pet_column_mapping=mapping_config.get("pet_column_mapping", {}),
            default_values=mapping_config.get("default_values", {}),
        )
    else:
        items = m_service.map_single_file(
            file_content=content1,
            column_mapping=mapping_config.get("column_mapping", {}),
            default_values=mapping_config.get("default_values", {}),
        )

    converted_bytes = m_service.generate_converted_excel(items)
    return StreamingResponse(
        io.BytesIO(converted_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=clientes_pets_migrados.xlsx"},
    )


@router.post("/migration/import", dependencies=[Depends(require_active_subscription)])
async def import_migration_files(
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    file2: UploadFile = File(None),
    config: str = Form(...),
    request: Request = None,
):
    """
    Converts 1 or 2 competitor Excel files in memory and starts a background import job immediately.
    """
    import json
    from app.modules.clients.migration_service import MigrationService
    m_service = MigrationService()

    try:
        mapping_config = json.loads(config)
    except Exception:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuração de mapeamento inválida")

    content1 = await file1.read()
    content2 = await file2.read() if file2 else None

    tenant_id = request.state.tenant_user.tenant_id
    is_two_files = mapping_config.get("mode") == "two_files" and content2 is not None

    if is_two_files:
        items = m_service.map_two_files(
            clients_file_content=content1,
            pets_file_content=content2,
            client_link_key=mapping_config.get("client_link_key", ""),
            pet_link_key=mapping_config.get("pet_link_key", ""),
            client_column_mapping=mapping_config.get("client_column_mapping", {}),
            pet_column_mapping=mapping_config.get("pet_column_mapping", {}),
            default_values=mapping_config.get("default_values", {}),
        )
    else:
        items = m_service.map_single_file(
            file_content=content1,
            column_mapping=mapping_config.get("column_mapping", {}),
            default_values=mapping_config.get("default_values", {}),
        )

    converted_bytes = m_service.generate_converted_excel(items)

    service = ClientService()
    job_id = create_job(tenant_id=tenant_id, job_type="clients")

    def _run_in_background():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                service.import_clients_from_excel_background(job_id, tenant_id, converted_bytes)
            )
        finally:
            loop.close()

    background_tasks.add_task(_run_in_background)

    return {"job_id": job_id, "total_items": len(items)}

