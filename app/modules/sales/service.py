from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List, Tuple, Optional

from .models import Sale, Comanda
from .schemas import SaleCreate, SaleUpdateStatus, ComandaSaveRequest
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

        # Validate discount and total amount mathematically (considering any unpaid remainder left in comanda)
        items_subtotal = sum(item.subtotal for item in data.items)
        expected_total = float(Decimal(str(items_subtotal)) - Decimal(str(data.discount_amount)))
        remainder = float(data.unpaid_remainder) if (data.unpaid_remainder and data.unpaid_remainder > 0.01) else 0.0
        expected_paid_now = float(Decimal(str(expected_total)) - Decimal(str(remainder)))

        if abs(data.total_amount - expected_paid_now) > 0.01:
             raise HTTPException(
                 status_code=400,
                 detail=f"O valor total da venda (R$ {data.total_amount:.2f}) somado ao saldo em aberto (R$ {remainder:.2f}) não corresponde ao subtotal dos itens (R$ {items_subtotal:.2f}) menos o desconto (R$ {data.discount_amount:.2f})."
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
                max_discount = float(tenant.max_discount_percentage) if tenant.max_discount_percentage is not None else 100.0
                # Float comparisons with small buffer
                if discount_percentage > (max_discount + 0.01):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Desconto de R$ {data.discount_amount:.2f} ({discount_percentage:.2f}%) excede o limite máximo permitido de {max_discount:.2f}%."
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
                     
        # 1.05 Validate unpaid remainder requires client
        if data.unpaid_remainder and data.unpaid_remainder > 0.01 and not data.client_id:
            raise HTTPException(
                status_code=400,
                detail="Para deixar saldo em aberto na comanda, é obrigatório selecionar um cliente."
            )

        # 1.1 Multi-payment validation & normalization
        if data.payments and len(data.payments) > 1:
            total_payments = sum(p.amount for p in data.payments)
            if abs(total_payments - data.total_amount) > 0.01:
                raise HTTPException(
                    status_code=400,
                    detail=f"A soma das formas de pagamento (R$ {total_payments:.2f}) não confere com o total da venda (R$ {data.total_amount:.2f})."
                )
            data.payment_method = "multiple"
        elif data.payments and len(data.payments) == 1:
            data.payment_method = data.payments[0].payment_method
            data.payments[0].amount = data.total_amount
        elif not data.payments:
            from .schemas import SalePaymentCreate
            data.payments = [SalePaymentCreate(payment_method=data.payment_method, amount=data.total_amount)]

        # 2. If everything is fine, create the sale in db (which marks comanda completed if linked)
        sale = self.repository.create(db, tenant_id, data)

        # 2.1 Link with active CashSession if available
        try:
            from app.modules.cash_register.repository import CashRegisterRepository
            from app.modules.cash_register.models import CashMovement

            cash_repo = CashRegisterRepository()
            active_session = cash_repo.get_active_session(db, tenant_id, data.cash_register_id)
            if active_session:
                sale.cash_session_id = active_session.id
                db.add(sale)

                # Calculate physical money received in this sale
                money_amount = 0.0
                if data.payments:
                    money_amount = sum(float(p.amount) for p in data.payments if p.payment_method == "money")
                elif data.payment_method == "money":
                    money_amount = float(sale.total_amount)

                if money_amount > 0:
                    latest_mov = cash_repo.get_latest_movement(db, active_session.id)
                    current_balance = float(latest_mov.balance_after) if latest_mov is not None else float(active_session.initial_amount)
                    new_balance = current_balance + money_amount

                    mov = CashMovement(
                        tenant_id=tenant_id,
                        session_id=active_session.id,
                        user_id=active_session.opened_by_user_id,
                        type="sale",
                        amount=round(money_amount, 2),
                        balance_after=round(new_balance, 2),
                        sale_id=sale.id,
                        destination_or_origin="Venda PDV",
                        description=f"Venda PDV #{sale.id}" + (f" (Dinheiro: R$ {money_amount:.2f})" if data.payment_method == "multiple" else ""),
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
                    # Vendendo novos pacotes direto pelo PDV (nascem pagos)
                    # Cria a quantidade exata comprada (ex: quantity=2 cria 2 pacotes independentes)
                    qty = max(1, getattr(item, "quantity", 1) or 1)
                    for _ in range(qty):
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
                comm_subtotal = Decimal(str(item.subtotal))
                if item.item_type == "service" and comm_subtotal <= Decimal("0"):
                    if item.unit_price and Decimal(str(item.unit_price)) > Decimal("0"):
                        comm_subtotal = Decimal(str(item.unit_price))
                    elif item.item_id:
                        from app.modules.services.models import Service
                        svc = db.query(Service).filter(Service.id == item.item_id).first()
                        if svc:
                            comm_subtotal = Decimal(svc.price_cents) / Decimal("100")

                self.commission_service.generate_entry(
                    db=db,
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    sale_item_id=item.id,
                    employee_id=item.employee_id,
                    service_id=item.item_id if item.item_type == "service" else None,
                    item_type=item.item_type,
                    subtotal=comm_subtotal,
                    ref_date=sale.created_at.date(),
                )
            except Exception:
                pass  # Não bloqueia a venda se a geração de comissão falhar

        db.commit()

        # 5. If linked to any appointments (directly, via items, or via comanda), mark them as completed
        linked_appointment_ids: set[int] = set()
        if data.appointment_id:
            linked_appointment_ids.add(data.appointment_id)
        for item in data.items:
            if getattr(item, "appointment_id", None):
                linked_appointment_ids.add(item.appointment_id)
        if sale.comanda:
            if sale.comanda.appointment_id:
                linked_appointment_ids.add(sale.comanda.appointment_id)
            for c_item in sale.comanda.items:
                if getattr(c_item, "appointment_id", None):
                    linked_appointment_ids.add(c_item.appointment_id)

        for apt_id in linked_appointment_ids:
            try:
                self.appointment_service.apply_action(
                    db=db,
                    tenant_id=tenant_id,
                    appointment_id=apt_id,
                    action="complete"
                )
            except HTTPException:
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

    def _revert_package_credits_for_item(self, db: Session, tenant_id: int, sale: Sale, item, reason: str | None = None) -> None:
        from app.modules.client_packages.models import ClientPackage, ClientPackageCredit, ClientPackageUsage
        from app.modules.appointments.models import AppointmentPackageCoverage, AppointmentItem

        if item.item_type == "package" and sale.client_id:
            client_pkg = (
                db.query(ClientPackage)
                .filter(
                    ClientPackage.tenant_id == tenant_id,
                    ClientPackage.client_id == sale.client_id,
                    ClientPackage.package_id == item.item_id,
                    ClientPackage.is_paid == True,
                )
                .order_by(ClientPackage.created_at.desc())
                .first()
            )
            if client_pkg:
                client_pkg.is_active = False
                client_pkg.is_paid = False
                db.add(client_pkg)

        reverted_credit = False
        if item.item_type == "service":
            appt_id = item.appointment_id or sale.appointment_id
            if appt_id:
                coverages = (
                    db.query(AppointmentPackageCoverage)
                    .join(AppointmentItem, AppointmentItem.id == AppointmentPackageCoverage.appointment_item_id)
                    .filter(
                        AppointmentItem.appointment_id == appt_id,
                        AppointmentPackageCoverage.service_id == item.item_id,
                    )
                    .all()
                )
                for cov in coverages:
                    if cov.client_package_credit_id:
                        credit = db.query(ClientPackageCredit).filter(ClientPackageCredit.id == cov.client_package_credit_id).first()
                        if credit:
                            credit.used_qty = max(0, credit.used_qty - 1)
                            db.add(credit)
                            client_pkg = credit.client_package
                            if client_pkg and not client_pkg.is_active:
                                client_pkg.is_active = True
                                db.add(client_pkg)
                            if client_pkg:
                                usage = ClientPackageUsage(
                                    tenant_id=tenant_id,
                                    client_package_id=client_pkg.id,
                                    credit_id=credit.id,
                                    change_qty=-1,
                                    notes=f"Estorno Item #{item.id} ({item.name}) da Venda #{sale.id}" + (f": {reason}" if reason else ""),
                                )
                                db.add(usage)
                            reverted_credit = True
                    db.delete(cov)

            is_package_service = (
                "(via pacote)" in (item.name or "").lower()
                or (float(item.subtotal or 0) == 0.0)
            )
            if is_package_service and not reverted_credit and sale.client_id:
                credit = (
                    db.query(ClientPackageCredit)
                    .join(ClientPackage, ClientPackage.id == ClientPackageCredit.client_package_id)
                    .filter(
                        ClientPackage.tenant_id == tenant_id,
                        ClientPackage.client_id == sale.client_id,
                        ClientPackageCredit.service_id == item.item_id,
                        ClientPackageCredit.used_qty > 0,
                    )
                    .order_by(ClientPackage.created_at.desc())
                    .first()
                )
                if credit:
                    credit.used_qty = max(0, credit.used_qty - 1)
                    db.add(credit)
                    client_pkg = credit.client_package
                    if client_pkg and not client_pkg.is_active:
                        client_pkg.is_active = True
                        db.add(client_pkg)
                    if client_pkg:
                        usage = ClientPackageUsage(
                            tenant_id=tenant_id,
                            client_package_id=client_pkg.id,
                            credit_id=credit.id,
                            change_qty=-1,
                            notes=f"Estorno Item #{item.id} ({item.name}) da Venda #{sale.id}" + (f": {reason}" if reason else ""),
                        )
                        db.add(usage)

    def _check_and_cancel_linked_appointments(
        self,
        db: Session,
        tenant_id: int,
        sale: Sale,
        appt_ids: set[int],
        reason: str | None = None,
    ) -> None:
        """
        When all services of an appointment have been canceled (via sale item cancellations,
        sale cancellation, etc.), automatically transitions the appointment to CANCELED status.
        Also cleans up any remaining commissions, package usages, and open comanda items.
        """
        from sqlalchemy import or_, func
        from app.modules.appointments.models import Appointment, AppointmentStatus, AppointmentPackageCoverage
        from app.modules.commissions.models import CommissionEntry
        from app.modules.sales.models import Sale, SaleItem, Comanda, ComandaItem

        for apt_id in appt_ids:
            if not apt_id:
                continue

            appointment = (
                db.query(Appointment)
                .filter(
                    Appointment.id == apt_id,
                    Appointment.tenant_id == tenant_id,
                )
                .first()
            )
            if not appointment or appointment.status == AppointmentStatus.CANCELED:
                continue

            # 1. Count active sale items linked to this appointment
            active_sale_items = (
                db.query(SaleItem)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.status != "canceled",
                    func.coalesce(SaleItem.status, "active") != "canceled",
                    or_(
                        SaleItem.appointment_id == apt_id,
                        (Sale.appointment_id == apt_id) & (SaleItem.item_type == "service"),
                    ),
                )
                .count()
            )

            # 2. Count active comanda items linked to this appointment (apenas serviços)
            active_comanda_items = (
                db.query(ComandaItem)
                .join(Comanda, Comanda.id == ComandaItem.comanda_id)
                .filter(
                    Comanda.tenant_id == tenant_id,
                    Comanda.status == "open",
                    ComandaItem.item_type == "service",
                    or_(
                        ComandaItem.appointment_id == apt_id,
                        Comanda.appointment_id == apt_id,
                    ),
                )
                .count()
            )

            # 3. Count active package coverages linked to this appointment's items
            item_ids = [item.id for item in appointment.items] if appointment.items else []
            active_coverages = 0
            if item_ids:
                active_coverages = (
                    db.query(AppointmentPackageCoverage)
                    .filter(AppointmentPackageCoverage.appointment_item_id.in_(item_ids))
                    .count()
                )

            # If no active sale items, no active comanda items, and no active package coverages remain:
            if active_sale_items == 0 and active_comanda_items == 0 and active_coverages == 0:
                appointment.status = AppointmentStatus.CANCELED
                cancel_note = "\n[Cancelado automaticamente: todos os serviços vinculados foram cancelados na venda]"
                if reason and reason.strip():
                    cancel_note += f" - Motivo: {reason.strip()}"
                appointment.notes = (appointment.notes or "") + cancel_note
                db.add(appointment)

                # Clean up any commissions for this appointment
                if item_ids:
                    try:
                        db.query(CommissionEntry).filter(
                            CommissionEntry.tenant_id == tenant_id,
                            CommissionEntry.appointment_item_id.in_(item_ids),
                        ).delete(synchronize_session=False)
                    except Exception:
                        pass

                # Clean up open comanda items if any
                comandas = (
                    db.query(Comanda)
                    .filter(
                        Comanda.tenant_id == tenant_id,
                        Comanda.status == "open",
                        or_(
                            Comanda.appointment_id == appointment.id,
                            Comanda.client_id == appointment.client_id,
                        ),
                    )
                    .all()
                )
                for comanda in comandas:
                    matching_items = [
                        ci for ci in list(comanda.items)
                        if ci.appointment_id == appointment.id or (
                            ci.item_type == "service" and comanda.appointment_id == appointment.id
                        )
                    ]
                    for ci in matching_items:
                        if ci in comanda.items:
                            comanda.items.remove(ci)
                        db.delete(ci)
                    db.flush()

                    if comanda.appointment_id == appointment.id:
                        other_appt_id = next((ci.appointment_id for ci in comanda.items if ci.appointment_id), None)
                        comanda.appointment_id = other_appt_id

                    remaining_subtotal = sum(ci.subtotal for ci in comanda.items)
                    comanda.total_amount = max(0.0, float(Decimal(str(remaining_subtotal)) - Decimal(str(comanda.discount_amount or 0))))
                    if not comanda.items or len(comanda.items) == 0:
                        db.delete(comanda)
                    else:
                        db.add(comanda)

    def cancel_sale(self, db: Session, tenant_id: int, sale_id: int, reason: str | None = None) -> Sale:
        sale = self.get_sale(db, tenant_id, sale_id)
        
        if sale.status == "canceled":
            raise HTTPException(status_code=400, detail="Venda já está cancelada.")

        # 1. Reverse the stock and package credits for all active items
        now = datetime.now(timezone.utc)
        for item in sale.items:
            if getattr(item, "status", "active") != "canceled":
                if item.item_type == "product":
                    self.product_service.adjust_stock(
                        db=db,
                        tenant_id=tenant_id,
                        product_id=item.item_id,
                        quantity_change=item.quantity,  # Positive quantity to cancel out
                        change_type="sale_cancel",
                        notes=f"Cancelamento Venda #{sale.id}" + (f": {reason}" if reason else "")
                    )
                elif item.item_type == "package":
                    package = self.package_service.get_package(db, tenant_id, item.item_id)
                    if package:
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
                self._revert_package_credits_for_item(db, tenant_id, sale, item, reason)
                item.status = "canceled"
                item.cancel_reason = reason
                item.canceled_at = now
                db.add(item)

        # 2. Cash movement reversal if any amount was paid in money and had a session (calcular antes de zerar total)
        money_amount = 0.0
        if sale.payments:
            money_amount = sum(float(p.amount) for p in sale.payments if p.payment_method == "money")
        elif sale.payment_method == "money":
            money_amount = float(sale.total_amount)

        # 3. Cancel sale and zero out total & payments
        sale.status = "canceled"
        sale.cancel_reason = reason
        sale.canceled_at = now
        sale.total_amount = Decimal("0.00")
        if sale.payments:
            for p in sale.payments:
                p.amount = Decimal("0.00")
                db.add(p)
        db.add(sale)

        if money_amount > 0 and sale.cash_session_id:
            try:
                from app.modules.cash_register.repository import CashRegisterRepository
                from app.modules.cash_register.models import CashMovement

                cash_repo = CashRegisterRepository()
                session = cash_repo.get_active_session(db, tenant_id) or cash_repo.get_session(db, tenant_id, sale.cash_session_id)
                if session and session.status == "open":
                    latest_mov = cash_repo.get_latest_movement(db, session.id)
                    current_balance = float(latest_mov.balance_after) if latest_mov is not None else float(session.initial_amount)
                    new_balance = current_balance - money_amount

                    cancel_mov = CashMovement(
                        tenant_id=tenant_id,
                        session_id=session.id,
                        user_id=session.opened_by_user_id,
                        type="sale_cancel",
                        amount=round(money_amount, 2),
                        balance_after=round(new_balance, 2),
                        sale_id=sale.id,
                        destination_or_origin="Cancelamento / Estorno",
                        description=f"Cancelamento de Venda #{sale.id}" + (f" (Dinheiro: R$ {money_amount:.2f})" if sale.payment_method == "multiple" else "") + (f": {reason}" if reason else ""),
                    )
                    cash_repo.create_movement(db, cancel_mov)
            except Exception:
                pass

        # 5. Check if linked appointments should be canceled
        db.flush()
        candidate_appt_ids = set()
        if sale.appointment_id:
            candidate_appt_ids.add(sale.appointment_id)
        for i in sale.items:
            if getattr(i, "appointment_id", None):
                candidate_appt_ids.add(i.appointment_id)

        if candidate_appt_ids:
            self._check_and_cancel_linked_appointments(db, tenant_id, sale, candidate_appt_ids, reason)

        db.commit()
        db.refresh(sale)
        return sale

    def cancel_sale_item(self, db: Session, tenant_id: int, sale_id: int, item_id: int, reason: str | None = None) -> Sale:
        sale = self.get_sale(db, tenant_id, sale_id)
        if sale.status == "canceled":
            raise HTTPException(status_code=400, detail="A venda já está totalmente cancelada.")

        item = next((i for i in sale.items if i.id == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado nesta venda.")

        if getattr(item, "status", "active") == "canceled":
            raise HTTPException(status_code=400, detail="Este item já foi cancelado/estornado.")

        now = datetime.now(timezone.utc)

        # 1. Reverse stock
        if item.item_type == "product":
            self.product_service.adjust_stock(
                db=db,
                tenant_id=tenant_id,
                product_id=item.item_id,
                quantity_change=item.quantity,
                change_type="sale_cancel",
                notes=f"Estorno Item #{item.id} Venda #{sale.id}" + (f": {reason}" if reason else "")
            )
        elif item.item_type == "package":
            package = self.package_service.get_package(db, tenant_id, item.item_id)
            if package:
                for p_item in package.items:
                    if p_item.product_id:
                        total_qty = p_item.quantity * item.quantity
                        self.product_service.adjust_stock(
                            db=db,
                            tenant_id=tenant_id,
                            product_id=p_item.product_id,
                            quantity_change=total_qty,
                            change_type="sale_cancel",
                            notes=f"Estorno Pacote em Venda #{sale.id}"
                        )

        # 1.1 Reverse package credits / sold client packages
        self._revert_package_credits_for_item(db, tenant_id, sale, item, reason)

        # 2. Mark item as canceled
        item.status = "canceled"
        item.cancel_reason = reason
        item.canceled_at = now
        db.add(item)

        # 3. Proportional cash refund if sale had cash payment
        money_amount = 0.0
        if sale.payments:
            money_paid = sum(float(p.amount) for p in sale.payments if p.payment_method == "money")
            total_sale = float(sale.total_amount)
            if total_sale > 0 and money_paid > 0:
                ratio = min(1.0, money_paid / total_sale)
                money_amount = round(float(item.subtotal) * ratio, 2)
        elif sale.payment_method == "money":
            money_amount = float(item.subtotal)

        if money_amount > 0 and sale.cash_session_id:
            try:
                from app.modules.cash_register.repository import CashRegisterRepository
                from app.modules.cash_register.models import CashMovement

                cash_repo = CashRegisterRepository()
                session = cash_repo.get_active_session(db, tenant_id) or cash_repo.get_session(db, tenant_id, sale.cash_session_id)
                if session and session.status == "open":
                    latest_mov = cash_repo.get_latest_movement(db, session.id)
                    current_balance = float(latest_mov.balance_after) if latest_mov is not None else float(session.initial_amount)
                    new_balance = current_balance - money_amount

                    cancel_mov = CashMovement(
                        tenant_id=tenant_id,
                        session_id=session.id,
                        user_id=session.opened_by_user_id,
                        type="sale_cancel",
                        amount=round(money_amount, 2),
                        balance_after=round(new_balance, 2),
                        sale_id=sale.id,
                        destination_or_origin="Cancelamento / Estorno Item",
                        description=f"Estorno Item '{item.name}' da Venda #{sale.id}" + (f" (Dinheiro: R$ {money_amount:.2f})" if sale.payment_method == "multiple" else "") + (f": {reason}" if reason else ""),
                    )
                    cash_repo.create_movement(db, cancel_mov)
            except Exception:
                pass

        # 4. Remove commission specific to this item
        try:
            from app.modules.commissions.models import CommissionEntry
            query = db.query(CommissionEntry).filter(
                CommissionEntry.tenant_id == tenant_id,
                CommissionEntry.sale_id == sale.id,
            )
            if item.item_type == "product":
                query = query.filter(CommissionEntry.product_id == item.item_id)
            elif item.appointment_id:
                query = query.filter(CommissionEntry.appointment_item_id == item.appointment_id)
            query.delete(synchronize_session=False)
        except Exception:
            pass

        # 5. Check if all items are now canceled and recalculate sale total & payments
        active_items = [i for i in sale.items if getattr(i, "status", "active") != "canceled"]
        if not active_items:
            sale.status = "canceled"
            sale.cancel_reason = f"Todos os itens cancelados" + (f": {reason}" if reason else "")
            sale.canceled_at = now
            sale.total_amount = Decimal("0.00")
            if sale.payments:
                for p in sale.payments:
                    p.amount = Decimal("0.00")
                    db.add(p)
        else:
            active_subtotal = sum(Decimal(str(i.subtotal)) for i in active_items)
            new_total = max(Decimal("0.00"), active_subtotal - Decimal(str(sale.discount_amount or 0)))
            sale.total_amount = new_total
            if sale.payments:
                old_total = sum(Decimal(str(p.amount)) for p in sale.payments)
                if old_total > Decimal("0.00"):
                    factor = new_total / old_total
                    running_sum = Decimal("0.00")
                    for idx, p in enumerate(sale.payments):
                        if idx == len(sale.payments) - 1:
                            p.amount = new_total - running_sum
                        else:
                            adjusted = (Decimal(str(p.amount)) * factor).quantize(Decimal("0.01"))
                            p.amount = adjusted
                            running_sum += adjusted
                        db.add(p)
        db.add(sale)
        db.flush()

        # 5. Check if linked appointments should be canceled
        candidate_appt_ids = set()
        if getattr(item, "appointment_id", None):
            candidate_appt_ids.add(item.appointment_id)
        if sale.appointment_id:
            candidate_appt_ids.add(sale.appointment_id)
        for i in sale.items:
            if getattr(i, "appointment_id", None):
                candidate_appt_ids.add(i.appointment_id)

        if candidate_appt_ids:
            self._check_and_cancel_linked_appointments(db, tenant_id, sale, candidate_appt_ids, reason)

        db.commit()
        db.refresh(sale)
        return sale

    # ── Comandas ────────────────────────────────────────────────────────────

    def save_open_comanda(self, db: Session, tenant_id: int, data: ComandaSaveRequest) -> Comanda:
        if not data.client_id:
            raise HTTPException(status_code=400, detail="É necessário informar um cliente para criar uma comanda em aberto.")

        from app.modules.clients.models import Client
        client = db.query(Client).filter(Client.id == data.client_id, Client.tenant_id == tenant_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        # Discount validation if > 0
        items_subtotal = sum(item.subtotal for item in data.items)
        if data.discount_amount > 0:
            from app.modules.tenants.models import Tenant
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant and not tenant.allow_discount:
                raise HTTPException(status_code=400, detail="Descontos estão desativados para esta empresa.")
            if tenant and items_subtotal > 0:
                discount_percentage = (data.discount_amount / items_subtotal) * 100
                max_discount = float(tenant.max_discount_percentage) if tenant.max_discount_percentage is not None else 100.0
                if discount_percentage > (max_discount + 0.01):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Desconto de R$ {data.discount_amount:.2f} ({discount_percentage:.2f}%) excede o limite permitido ({max_discount:.2f}%)."
                    )

        return self.repository.save_open_comanda(db, tenant_id, data)

    def get_comanda(self, db: Session, tenant_id: int, comanda_id: int) -> Comanda:
        comanda = self.repository.get_comanda(db, tenant_id, comanda_id)
        if not comanda:
            raise HTTPException(status_code=404, detail="Comanda não encontrada.")
        return comanda

    def sync_client_open_comanda(self, db: Session, tenant_id: int, client_id: int) -> Comanda | None:
        from app.modules.appointments.models import Appointment
        from app.modules.appointments.schemas import AppointmentResponse
        from sqlalchemy.orm import selectinload

        comanda = self.repository.get_client_open_comanda(db, tenant_id, client_id)

        # Buscar agendamentos finalizados do cliente para checar pendências
        appts = (
            db.query(Appointment)
            .options(
                selectinload(Appointment.items),
                selectinload(Appointment.sales),
                selectinload(Appointment.sale_items),
            )
            .filter(
                Appointment.tenant_id == tenant_id,
                Appointment.client_id == client_id,
                Appointment.status == "completed",
            )
            .order_by(Appointment.scheduled_at.asc())
            .all()
        )

        existing_keys = set()
        items_changed = False
        completed_appt_ids = {a.id for a in appts}

        if comanda and comanda.items:
            # Limpar serviços de agendamentos que não estão mais finalizados/ativos (ex: cancelados)
            stale_items = [
                ci for ci in list(comanda.items)
                if ci.item_type == "service" and ci.appointment_id and ci.appointment_id not in completed_appt_ids
            ]
            if stale_items:
                for si in stale_items:
                    comanda.items.remove(si)
                    db.delete(si)
                items_changed = True

            if comanda.appointment_id and comanda.appointment_id not in completed_appt_ids:
                other_appt_id = next((ci.appointment_id for ci in comanda.items if ci.appointment_id), None)
                comanda.appointment_id = other_appt_id
                items_changed = True

            existing_keys = {
                (ci.appointment_id, ci.item_id)
                for ci in comanda.items
                if ci.appointment_id and ci.item_type == "service"
            }

        items_added = False
        for a in appts:
            resp = AppointmentResponse.model_validate(a)
            if resp.is_paid or resp.is_fully_package_covered:
                continue

            emp_map = {}
            for it in a.items:
                for ais in getattr(it, "item_services", []):
                    emp_map[ais.service_id] = ais.employee_id

            for item_resp in resp.items:
                for s in item_resp.services:
                    if (a.id, s.id) in existing_keys:
                        continue

                    if not comanda:
                        comanda = Comanda(
                            tenant_id=tenant_id,
                            client_id=client_id,
                            appointment_id=a.id,
                            status="open",
                            total_amount=0.0,
                            discount_amount=0.0,
                        )
                        db.add(comanda)
                        db.flush()

                    real_price = float(Decimal(s.price_cents) / Decimal("100"))
                    subtotal = 0.0 if s.is_package_covered else real_price
                    name = f"{s.name} (via pacote)" if s.is_package_covered else s.name

                    c_item = ComandaItem(
                        comanda_id=comanda.id,
                        item_type="service",
                        item_id=s.id,
                        name=name,
                        quantity=1,
                        unit_price=real_price,
                        subtotal=subtotal,
                        employee_id=s.employee_id or emp_map.get(s.id),
                        pet_ids=[item_resp.pet.id] if item_resp.pet else None,
                        unit="UN",
                        appointment_id=a.id,
                    )
                    db.add(c_item)
                    existing_keys.add((a.id, s.id))
                    items_added = True

        if comanda:
            if not comanda.items or len(comanda.items) == 0:
                db.delete(comanda)
                db.commit()
                return None
            elif items_added or items_changed:
                db.flush()
                db.refresh(comanda)
                total = sum(Decimal(str(ci.subtotal)) for ci in comanda.items)
                comanda.total_amount = max(0.0, float(total - Decimal(str(comanda.discount_amount or 0))))
                db.commit()
                db.refresh(comanda)

        return comanda

    def get_client_open_comanda(self, db: Session, tenant_id: int, client_id: int) -> Comanda | None:
        return self.sync_client_open_comanda(db, tenant_id, client_id)

    def list_open_comandas(
        self, db: Session, tenant_id: int, search: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict:
        items, total = self.repository.list_open_comandas(db, tenant_id, search=search, limit=limit, offset=offset)
        return {"items": items, "total": total}

    def delete_comanda(self, db: Session, tenant_id: int, comanda_id: int) -> dict:
        success = self.repository.delete_comanda(db, tenant_id, comanda_id)
        if not success:
            raise HTTPException(status_code=404, detail="Comanda em aberto não encontrada para exclusão.")
        return {"ok": True}
