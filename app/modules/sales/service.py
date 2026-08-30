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
        # 0. Validate that cash register is open
        from app.modules.cash_register.repository import CashRegisterRepository
        cash_repo = CashRegisterRepository()
        active_session = cash_repo.get_active_session(db, tenant_id)
        if not active_session:
            raise HTTPException(
                status_code=400,
                detail="O caixa está fechado. É necessário abrir o caixa antes de realizar vendas."
            )

        # Validate discount and total amount mathematically
        items_subtotal = sum(item.subtotal for item in data.items)
        expected_total = float(Decimal(str(items_subtotal)) - Decimal(str(data.discount_amount)))
        if abs(data.total_amount - expected_total) > 0.01:
             raise HTTPException(
                 status_code=400,
                 detail=f"O valor total da venda (R$ {data.total_amount:.2f}) não corresponde ao subtotal dos itens (R$ {items_subtotal:.2f}) menos o desconto (R$ {data.discount_amount:.2f})."
             )

        if data.discount_amount > 0:
            from app.modules.tenants.models import Tenant
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise HTTPException(status_code=400, detail="Tenant não encontrado.")
            
            if not tenant.allow_discount:
                raise HTTPException(status_code=400, detail="Descontos estão desativados para esta empresa.")
            
            if items_subtotal > 0:
                discount_percentage = (data.discount_amount / items_subtotal) * 100
                # Float comparisons with small buffer
                if discount_percentage > (tenant.max_discount_percentage + 0.01):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Desconto de R$ {data.discount_amount:.2f} ({discount_percentage:.2f}%) excede o limite máximo permitido de {tenant.max_discount_percentage:.2f}%."
                    )
        
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
                if not package:
                    raise HTTPException(status_code=400, detail=f"Pacote com ID {item.item_id} não encontrado.")
                
                if not data.client_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Para vender o pacote '{item.name}', é necessário selecionar um cliente."
                    )
                if not item.pet_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Para vender o pacote '{item.name}', é necessário selecionar pelo menos um pet."
                    )

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

        # 2.1 Link with active CashSession if available
        try:
            from app.modules.cash_register.repository import CashRegisterRepository
            from app.modules.cash_register.models import CashMovement

            cash_repo = CashRegisterRepository()
            active_session = cash_repo.get_active_session(db, tenant_id)
            if active_session:
                sale.cash_session_id = active_session.id
                db.add(sale)

                if data.payment_method == "money":
                    latest_mov = cash_repo.get_latest_movement(db, active_session.id)
                    current_balance = float(latest_mov.balance_after) if latest_mov is not None else float(active_session.initial_amount)
                    new_balance = current_balance + float(sale.total_amount)

                    mov = CashMovement(
                        tenant_id=tenant_id,
                        session_id=active_session.id,
                        user_id=active_session.opened_by_user_id,
                        type="sale",
                        amount=float(sale.total_amount),
                        balance_after=round(new_balance, 2),
                        sale_id=sale.id,
                        destination_or_origin="Venda PDV",
                        description=f"Venda PDV #{sale.id}",
                    )
                    cash_repo.create_movement(db, mov)
        except Exception:
            pass  # Não bloqueia a venda caso haja inconsistência de caixa

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
                elif item.pet_ids and data.client_id:
                    # Vendendo um novo pacote direto pelo PDV (nasce pago)
                    # Não colocamos try/except geral para que erros de validação subam e cancelem a transação
                    self.client_package_service.sell(
                        db=db,
                        tenant_id=tenant_id,
                        client_id=data.client_id,
                        data=ClientPackageSellRequest(
                            pet_ids=item.pet_ids,
                            package_id=item.item_id,
                        ),
                        is_paid=True, # Vendido no PDV já é pago
                    )

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

    def list_sales(self, db: Session, tenant_id: int, skip: int = 0, limit: int = 100, start_date=None, end_date=None, client_id: int | None = None) -> List[Sale]:
        return self.repository.list(db, tenant_id, skip, limit, start_date=start_date, end_date=end_date, client_id=client_id)

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

        # 3. Cash movement reversal if it was paid in money and had a session
        if sale.payment_method == "money" and sale.cash_session_id:
            try:
                from app.modules.cash_register.repository import CashRegisterRepository
                from app.modules.cash_register.models import CashMovement

                cash_repo = CashRegisterRepository()
                session = cash_repo.get_active_session(db, tenant_id) or cash_repo.get_session(db, tenant_id, sale.cash_session_id)
                if session and session.status == "open":
                    latest_mov = cash_repo.get_latest_movement(db, session.id)
                    current_balance = float(latest_mov.balance_after) if latest_mov is not None else float(session.initial_amount)
                    new_balance = current_balance - float(sale.total_amount)

                    cancel_mov = CashMovement(
                        tenant_id=tenant_id,
                        session_id=session.id,
                        user_id=session.opened_by_user_id,
                        type="sale_cancel",
                        amount=float(sale.total_amount),
                        balance_after=round(new_balance, 2),
                        sale_id=sale.id,
                        destination_or_origin="Cancelamento / Estorno",
                        description=f"Cancelamento de Venda #{sale.id}",
                    )
                    cash_repo.create_movement(db, cancel_mov)
            except Exception:
                pass

        return updated_sale
