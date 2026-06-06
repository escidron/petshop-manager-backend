import io
from fastapi import APIRouter, Depends, Request, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import ProductCreate, ProductUpdate, ProductResponse
from .inventory_schemas import InventoryLogResponse, StockAdjustmentRequest, GlobalInventoryLogResponse
from .service import ProductService

router = APIRouter(prefix="/products", tags=["Produtos"], dependencies=[Depends(get_current_tenant)])


@router.get("/inventory/logs", response_model=list[GlobalInventoryLogResponse])
def get_global_inventory_logs(skip: int = 0, limit: int = 100, request: Request = None, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.inventory_repository.list_all_logs(db, tenant_id, skip, limit)


@router.post("/", response_model=ProductResponse)
def create_product(data: ProductCreate, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.create_product(db, tenant_id, data)


@router.get("/", response_model=list[ProductResponse])
def list_products(request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.list_products(db, tenant_id)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.get_product(db, tenant_id, product_id)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, data: ProductUpdate, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.update_product(db, tenant_id, product_id, data)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    service.delete_product(db, tenant_id, product_id)

@router.get("/{product_id}/inventory", response_model=list[InventoryLogResponse])
def list_inventory_logs(product_id: int, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    # We need to add a method to service to list logs
    return service.inventory_repository.list_logs(db, tenant_id, product_id)

@router.post("/{product_id}/adjust-stock", response_model=ProductResponse)
def adjust_stock(product_id: int, data: StockAdjustmentRequest, request: Request, db: Session = Depends(get_db)):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    return service.adjust_stock(
        db, 
        tenant_id, 
        product_id, 
        data.quantity_change, 
        data.change_type, 
        data.notes
    )
    
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
        headers={"Content-Disposition": "attachment; filename=template_produtos.xlsx"}
    )

@router.post("/import")
async def import_products(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    service = ProductService()
    tenant_id = request.state.tenant_user.tenant_id
    content = await file.read()
    return await service.import_products_from_excel(db, tenant_id, content)
