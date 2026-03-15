from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List

from .models import Sale
from .schemas import SaleCreate, SaleUpdateStatus
from .repository import SalesRepository
from app.modules.products.service import ProductService
from app.modules.appointments.service import AppointmentService

class SalesService:
    def __init__(self):
        self.repository = SalesRepository()
        self.product_service = ProductService()
        self.appointment_service = AppointmentService()

    def create_sale(self, db: Session, tenant_id: int, data: SaleCreate) -> Sale:
        
        # 1. First, validate stock and lower the stock for products BEFORE creating the sale
        for item in data.items:
            if item.item_type == "product":
                product = self.product_service.get_product(db, tenant_id, item.item_id)
                if not product:
                    raise HTTPException(status_code=400, detail=f"Produto com ID {item.item_id} não encontrado.")
                
                # Low stock is handled by adjust_stock which will raise exception if new quantity < 0
                try:
                    self.product_service.adjust_stock(
                        db=db,
                        tenant_id=tenant_id,
                        product_id=item.item_id,
                        quantity_change=-item.quantity,  # Negative quantity for sale
                        change_type="sale",
                        notes=f"Venda no PDV"
                    )
                except HTTPException as e:
                     raise HTTPException(status_code=400, detail=f"Estoque insuficiente para {item.name}. {e.detail}")
                     
        # 2. If everything is fine, create the sale in db
        sale = self.repository.create(db, tenant_id, data)

        # 3. If it's linked to an appointment, mark appointment as completed
        if data.appointment_id:
            try:
                self.appointment_service.apply_action(
                    db=db,
                    tenant_id=tenant_id,
                    appointment_id=data.appointment_id,
                    action="complete"
                )
            except HTTPException as e:
                # We don't want to fail the sale if the appointment status update fails, 
                # but we should probably log it. For now, just continue.
                pass

        return sale

    def get_sale(self, db: Session, tenant_id: int, sale_id: int) -> Sale:
        sale = self.repository.get(db, tenant_id, sale_id)
        if not sale:
            raise HTTPException(status_code=404, detail="Venda não encontrada.")
        return sale

    def list_sales(self, db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[Sale]:
        return self.repository.list(db, tenant_id, skip, limit)

    def cancel_sale(self, db: Session, tenant_id: int, sale_id: int) -> Sale:
        sale = self.get_sale(db, tenant_id, sale_id)
        
        if sale.status == "canceled":
            raise HTTPException(status_code=400, detail="Venda já está cancelada.")

        # 1. Reverse the stock
        for item in sale.items:
             if item.item_type == "product":
                 self.product_service.adjust_stock(
                        db=db,
                        tenant_id=tenant_id,
                        product_id=item.item_id,
                        quantity_change=item.quantity, # Positive quantity to cancel out
                        change_type="sale_cancel",
                        notes=f"Cancelamento Venda #{sale.id}"
                    )

        # 2. Cancel sale
        updated_sale = self.repository.update_status(db, tenant_id, sale_id, "canceled")
        return updated_sale
