from sqlalchemy.orm import Session
from .inventory_models import InventoryLog
from .models import Product

class InventoryRepository:
    def create_log(
        self, 
        db: Session, 
        tenant_id: int, 
        product_id: int, 
        quantity_change: int, 
        change_type: str, 
        notes: str | None = None
    ) -> InventoryLog:
        log = InventoryLog(
            tenant_id=tenant_id,
            product_id=product_id,
            quantity_change=quantity_change,
            change_type=change_type,
            notes=notes
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def list_logs(self, db: Session, tenant_id: int, product_id: int | None = None) -> list[InventoryLog]:
        query = db.query(InventoryLog).filter(InventoryLog.tenant_id == tenant_id)
        if product_id:
            query = query.filter(InventoryLog.product_id == product_id)
        return query.order_by(InventoryLog.created_at.desc()).all()
