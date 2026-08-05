import asyncio
import io
from fastapi import APIRouter, BackgroundTasks, Depends, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session



from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription, require_owner
from .schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
)
from .service import ServiceService

router = APIRouter(prefix="/services", tags=["Services"], dependencies=[Depends(get_current_tenant)])

@router.get("/export", dependencies=[Depends(require_owner)])
def export_services(
    request: Request,
    db: Session = Depends(get_db),
):
    service = ServiceService()
    tenant_id = request.state.tenant_user.tenant_id
    excel_data = service.export_to_excel(db, tenant_id)
    return StreamingResponse(
        io.BytesIO(excel_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="backup_servicos.xlsx"'}
    )


@router.post("/", response_model=ServiceResponse, dependencies=[Depends(require_active_subscription)])
def create_service(
    data: ServiceCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().create(db, tenant_id, data)


@router.get("/", response_model=list[ServiceResponse])
def list_services(
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().list(db, tenant_id)


@router.patch("/{service_id}", response_model=ServiceResponse, dependencies=[Depends(require_active_subscription)])
def update_service(
    service_id: int,
    data: ServiceUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return ServiceService().update(db, tenant_id, service_id, data)


@router.delete("/{service_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_service(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    ServiceService().delete(db, tenant_id, service_id)


@router.get("/import/template")
def get_import_template():
    import io
    from fastapi.responses import StreamingResponse
    content = ServiceService().generate_import_template_excel()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_servicos.xlsx"},
    )


@router.post("/import", dependencies=[Depends(require_active_subscription)])
async def import_services(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    import asyncio
    from app.modules.clients.import_jobs import create_job
    service = ServiceService()
    tenant_id = request.state.tenant_user.tenant_id
    file_content = await file.read()

    job_id = create_job(tenant_id=tenant_id, job_type="services")

    def _run_in_background():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                service.import_services_from_excel_background(job_id, tenant_id, file_content)
            )
        finally:
            loop.close()

    background_tasks.add_task(_run_in_background)

    return {"job_id": job_id}


@router.get("/import/status/{job_id}")
def get_import_status(job_id: str):
    from app.modules.clients.import_jobs import get_job
    from fastapi import HTTPException, status
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job não encontrado")
    return job


# ---------------------------------------------------------------------------
# Services Migration Wizard Endpoints
# ---------------------------------------------------------------------------
@router.post("/migration/inspect", dependencies=[Depends(require_active_subscription)])
async def inspect_service_migration_file(file1: UploadFile = File(...)):
    from app.modules.tenant_services.migration_service import ServiceMigrationService
    s_service = ServiceMigrationService()
    content = await file1.read()
    headers = s_service.inspect_excel_headers(content)
    return {"file1_headers": headers}


@router.post("/migration/convert", dependencies=[Depends(require_active_subscription)])
async def convert_service_migration_file(
    file1: UploadFile = File(...),
    config: str = Form(...),
):
    import json
    from app.modules.tenant_services.migration_service import ServiceMigrationService
    s_service = ServiceMigrationService()
    try:
        mapping_config = json.loads(config)
    except Exception:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuração inválida")

    content = await file1.read()
    items = s_service.map_file(
        file_content=content,
        column_mapping=mapping_config.get("column_mapping", {}),
        default_values=mapping_config.get("default_values", {}),
    )
    converted_bytes = s_service.generate_converted_excel(items)
    return StreamingResponse(
        io.BytesIO(converted_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=servicos_migrados.xlsx"},
    )


@router.post("/migration/import", dependencies=[Depends(require_active_subscription)])
async def import_service_migration_file(
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    config: str = Form(...),
    request: Request = None,
):
    import json
    from app.modules.tenant_services.migration_service import ServiceMigrationService
    from app.modules.clients.import_jobs import create_job

    s_service = ServiceMigrationService()
    try:
        mapping_config = json.loads(config)
    except Exception:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuração inválida")

    content = await file1.read()
    items = s_service.map_file(
        file_content=content,
        column_mapping=mapping_config.get("column_mapping", {}),
        default_values=mapping_config.get("default_values", {}),
    )
    converted_bytes = s_service.generate_converted_excel(items)

    service = ServiceService()
    tenant_id = request.state.tenant_user.tenant_id
    job_id = create_job(tenant_id=tenant_id, job_type="services")

    def _run_in_background():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                service.import_services_from_excel_background(job_id, tenant_id, converted_bytes)
            )
        finally:
            loop.close()

    background_tasks.add_task(_run_in_background)
    return {"job_id": job_id, "total_items": len(items)}

