from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List

from .models import Sale
from .schemas import SaleCreate, SaleUpdateStatus
from .repository import SalesRepository
from app.modules.products.service import ProductService
from app.modules.appointments.service import AppointmentService
from app.modules.packages.service import PackageService
from app.modules.client_packages.service import ClientPackageService
from app.modules.client_packages.schemas import ClientPackageSellRequest
from app.modules.commissions.service import CommissionService

class SalesService:
    def __init__(self):
        self.repository = SalesRepository()
        self.product_service = ProductService()
        self.appointment_service = AppointmentService()
        self.package_service = PackageService()
        self.client_package_service = ClientPackageService()
        self.commission_service = CommissionService()

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
                        quantity_change=-item.quantity,
                        change_type="sale",
                        notes=f"Venda no PDV"
                    )
                except HTTPException as e:
                     raise HTTPException(status_code=400, detail=f"Estoque insuficiente para {item.name}. {e.detail}")
            
            elif item.item_type == "package":
                package = self.package_service.get_package(db, tenant_id, item.item_id)
                for p_item in package.items:
                    if p_item.product_id:
                        total_qty = p_item.quantity * item.quantity
                        try:
                            self.product_service.adjust_stock(
                                db=db,
                                tenant_id=tenant_id,
                                product_id=p_item.product_id,
                                quantity_change=-total_qty,
                                change_type="sale",
                                notes=f"Venda de Pacote: {package.name}"
                            )
                        except HTTPException as e:
                            raise HTTPException(status_code=400, detail=f"Estoque insuficiente no pacote {package.name}. {e.detail}")
                     
        # 2. If everything is fine, create the sale in db
        sale = self.repository.create(db, tenant_id, data)

        # 3. Auto-create or mark-as-paid ClientPackage
        for item in data.items:
            if item.item_type == "package":
                if hasattr(item, "client_package_id_to_pay") and item.client_package_id_to_pay:
                    # Pagando um pacote pendente
                    try:
                        pkg = self.client_package_service.repo.get_by_id_scoped(db, tenant_id, item.client_package_id_to_pay)
                        if pkg and not pkg.is_paid:
                            pkg.is_paid = True
                            db.add(pkg)
                    except Exception:
                        pass
                elif item.pet_id and data.client_id:
                    # Vendendo um novo pacote direto pelo PDV (nasce pago)
                    try:
                        self.client_package_service.sell(
                            db=db,
                            tenant_id=tenant_id,
                            client_id=data.client_id,
                            data=ClientPackageSellRequest(
                                pet_id=item.pet_id,
                                package_id=item.item_id,
                            ),
                            is_paid=True, # Vendido no PDV já é pago
                        )
                    except HTTPException:
                        pass

        # 4. Generate commission entries for items with employee_id
        for item in sale.items:
            if not item.employee_id:
                continue
            try:
                self.commission_service.generate_entry(
                    db=db,
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    sale_item_id=item.id,
                    employee_id=item.employee_id,
                    service_id=item.item_id if item.item_type == "service" else None,
                    item_type=item.item_type,
                    subtotal=Decimal(str(item.subtotal)),
                    ref_date=sale.created_at.date(),
                )
            except Exception:
                pass  # Não bloqueia a venda se a geração de comissão falhar

        db.commit()

        # 5. If it's linked to an appointment, mark appointment as completed
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

    def list_sales(self, db: Session, tenant_id: int, skip: int = 0, limit: int = 100, start_date=None, end_date=None) -> List[Sale]:
        return self.repository.list(db, tenant_id, skip, limit, start_date=start_date, end_date=end_date)

    def assign_employee_to_item(
        self, db: Session, tenant_id: int, sale_id: int, item_id: int, employee_id: int
    ) -> Sale:
        sale = self.get_sale(db, tenant_id, sale_id)
        item = next((i for i in sale.items if i.id == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado nesta venda.")
        if item.employee_id is not None:
            raise HTTPException(
                status_code=400,
                detail="Funcionário já atribuído a este item. Comissão existente não pode ser sobrescrita.",
            )

        item.employee_id = employee_id
        db.flush()

        try:
            self.commission_service.generate_retroactive(
                db=db,
                tenant_id=tenant_id,
                sale_id=sale.id,
                sale_item_id=item.id,
                employee_id=employee_id,
                service_id=item.item_id if item.item_type == "service" else None,
                item_type=item.item_type,
                subtotal=Decimal(str(item.subtotal)),
                ref_date=sale.created_at.date(),
            )
        except HTTPException:
            pass

        db.commit()
        db.refresh(sale)
        return sale

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
             
             elif item.item_type == "package":
                 package = self.package_service.get_package(db, tenant_id, item.item_id)
                 for p_item in package.items:
                     if p_item.product_id:
                         total_qty = p_item.quantity * item.quantity
                         self.product_service.adjust_stock(
                             db=db,
                             tenant_id=tenant_id,
                             product_id=p_item.product_id,
                             quantity_change=total_qty,
                             change_type="sale_cancel",
                             notes=f"Cancelamento Pacote em Venda #{sale.id}"
                         )

        # 2. Cancel sale
        updated_sale = self.repository.update_status(db, tenant_id, sale_id, "canceled")
        return updated_sale
