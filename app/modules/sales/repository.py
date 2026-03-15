from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import Sale, SaleItem
from .schemas import SaleCreate

class SalesRepository:
    def create(self, db: Session, tenant_id: int, data: SaleCreate) -> Sale:
        db_sale = Sale(
            tenant_id=tenant_id,
            client_id=data.client_id,
            pet_id=data.pet_id,
            total_amount=data.total_amount,
            payment_method=data.payment_method,
            status=data.status
        )
        db.add(db_sale)
        db.flush() # Flush to get db_sale.id

        for item in data.items:
            db_item = SaleItem(
                sale_id=db_sale.id,
                item_type=item.item_type,
                item_id=item.item_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal
            )
            db.add(db_item)

        db.commit()
        db.refresh(db_sale)
        return db_sale

    def get(self, db: Session, tenant_id: int, sale_id: int) -> Sale | None:
        return db.query(Sale).filter(
            Sale.id == sale_id,
            Sale.tenant_id == tenant_id
        ).first()

    def list(self, db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> list[Sale]:
        return db.query(Sale).filter(
            Sale.tenant_id == tenant_id
        ).order_by(desc(Sale.created_at)).offset(skip).limit(limit).all()

    def update_status(self, db: Session, tenant_id: int, sale_id: int, status: str) -> Sale | None:
        db_sale = self.get(db, tenant_id, sale_id)
        if db_sale:
            db_sale.status = status
            db.commit()
            db.refresh(db_sale)
            return db_sale
        return None
