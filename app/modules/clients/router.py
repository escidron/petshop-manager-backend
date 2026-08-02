import asyncio
import io
from fastapi import APIRouter, BackgroundTasks, Depends, Request, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
)
from .service import ClientService
from .import_jobs import create_job, get_job

router = APIRouter(prefix="/clients", tags=["Clients"], dependencies=[Depends(get_current_tenant)])



@router.post("/", response_model=ClientResponse, dependencies=[Depends(require_active_subscription)])
def create_client(
    data: ClientCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    service = ClientService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_client(db, tenant_id, data)


@router.get("/", response_model=list[ClientResponse])
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
