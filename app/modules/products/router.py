import asyncio
import io
from fastapi import APIRouter, BackgroundTasks, Depends, Request, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session


from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import ProductCreate, ProductUpdate, ProductResponse
from .inventory_schemas import InventoryLogResponse, StockAdjustmentRequest, GlobalInventoryLogResponse
from .service import ProductService

router = APIRouter(prefix="/products", tags=["Produtos"], dependencies=[Depends(get_current_tenant)])


@router.get("/inventory/logs", response_model=list[GlobalInventoryLogResponse])
def get_global_inventory_logs(skip: int = 0, limit: int = 100, request: Request = None, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.inventory_repository.list_all_logs(db, tenant_id, skip, limit)


@router.post("/", response_model=ProductResponse, dependencies=[Depends(require_active_subscription)])
def create_product(data: ProductCreate, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_product(db, tenant_id, data)


@router.get("/", response_model=list[ProductResponse])
def list_products(exclude_internal: bool = False, request: Request = None, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_products(db, tenant_id, exclude_internal=exclude_internal)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_product(db, tenant_id, product_id)


@router.patch("/{product_id}", response_model=ProductResponse, dependencies=[Depends(require_active_subscription)])
def update_product(product_id: int, data: ProductUpdate, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_product(db, tenant_id, product_id, data)


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_product(db, tenant_id, product_id)


@router.get("/{product_id}/inventory", response_model=list[InventoryLogResponse])
def list_inventory_logs(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.inventory_repository.list_logs(db, tenant_id, product_id)


@router.post("/{product_id}/adjust-stock", response_model=ProductResponse, dependencies=[Depends(require_active_subscription)])
def adjust_stock(product_id: int, data: StockAdjustmentRequest, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.adjust_stock(db, tenant_id, product_id, data.quantity_change, data.change_type, data.notes)


@router.get("/inventory/low-stock", response_model=list[ProductResponse])
def list_low_stock_products(request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    all_products = service.list_products(db, tenant_id)
    return [p for p in all_products if p.quantity <= p.min_stock]


@router.get("/import/template")
def get_import_template():
    service = ProductService()
    content = service.generate_import_template_excel()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_produtos.xlsx"},
    )


@router.post("/import", dependencies=[Depends(require_active_subscription)])
async def import_products(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    from app.modules.clients.import_jobs import create_job
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    file_content = await file.read()

    job_id = create_job(tenant_id=tenant_id, job_type="products")

    def _run_in_background():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                service.import_products_from_excel_background(job_id, tenant_id, file_content)
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

