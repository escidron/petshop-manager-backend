from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import desc, func, or_

from .models import Sale, SaleItem, SalePayment, Comanda, ComandaItem
from .schemas import SaleCreate, ComandaSaveRequest
from app.modules.clients.models import Client
from app.modules.appointments.models import Appointment, AppointmentItem
from app.modules.pets.models import Pet


def _sale_eager_options():
    return [
        selectinload(Sale.items),
        selectinload(Sale.payments),
        joinedload(Sale.pet),
        joinedload(Sale.client).selectinload(Client.pets),
        joinedload(Sale.appointment).joinedload(Appointment.client).selectinload(Client.pets),
        joinedload(Sale.appointment).selectinload(Appointment.items).selectinload(AppointmentItem.services),
        joinedload(Sale.appointment).selectinload(Appointment.items).joinedload(AppointmentItem.pet),
    ]


class SalesRepository:
    def create(self, db: Session, tenant_id: int, data: SaleCreate) -> Sale:
        db_sale = Sale(
            tenant_id=tenant_id,
            client_id=data.client_id,
            pet_id=data.pet_id,
            appointment_id=data.appointment_id,
            comanda_id=data.comanda_id,
            total_amount=data.total_amount,
            discount_amount=data.discount_amount,
            payment_method=data.payment_method,
            status=data.status,
        )
        db.add(db_sale)
        db.flush()  # Flush to get db_sale.id

        if data.payments:
            for p in data.payments:
                db_payment = SalePayment(
                    sale_id=db_sale.id,
                    payment_method=p.payment_method,
                    amount=p.amount,
                )
                db.add(db_payment)
        else:
            db_payment = SalePayment(
                sale_id=db_sale.id,
                payment_method=data.payment_method,
                amount=data.total_amount,
            )
            db.add(db_payment)

        for item in data.items:
            db_item = SaleItem(
                sale_id=db_sale.id,
                item_type=item.item_type,
                item_id=item.item_id,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
                employee_id=item.employee_id,
                appointment_id=item.appointment_id if item.item_type == "service" else None,
            )
            db.add(db_item)

        # If linked to a comanda (or if an open comanda exists for this appointment/client)
        target_comanda = None
        if data.comanda_id:
            target_comanda = db.query(Comanda).filter(
                Comanda.id == data.comanda_id,
                Comanda.tenant_id == tenant_id,
            ).first()
        elif data.appointment_id:
            target_comanda = db.query(Comanda).filter(
                Comanda.appointment_id == data.appointment_id,
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
            ).first()
        elif data.client_id:
            target_comanda = db.query(Comanda).filter(
                Comanda.client_id == data.client_id,
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
            ).first()

        if data.unpaid_remainder and data.unpaid_remainder > 0.01 and data.client_id:
            remainder_val = round(float(data.unpaid_remainder), 2)
            if not target_comanda:
                target_comanda = Comanda(
                    tenant_id=tenant_id,
                    client_id=data.client_id,
                    appointment_id=data.appointment_id,
                    status="open",
                    total_amount=remainder_val,
                    discount_amount=0.0,
                )
                db.add(target_comanda)
                db.flush()
            else:
                target_comanda.status = "open"
                target_comanda.total_amount = remainder_val
                target_comanda.discount_amount = 0.0
                target_comanda.items.clear()
                db.flush()

            c_item = ComandaItem(
                comanda_id=target_comanda.id,
                item_type="service",
                item_id=0,
                name="Saldo em Aberto (Comanda)",
                quantity=1,
                unit_price=remainder_val,
                subtotal=remainder_val,
            )
            db.add(c_item)
            db_sale.comanda_id = target_comanda.id
        elif target_comanda:
            target_comanda.status = "completed"
            db_sale.comanda_id = target_comanda.id
            db.add(target_comanda)

        db.commit()
        db.refresh(db_sale)
        return db_sale

    def get(self, db: Session, tenant_id: int, sale_id: int) -> Sale | None:
        return (
            db.query(Sale)
            .options(*_sale_eager_options())
            .filter(
                Sale.id == sale_id,
                Sale.tenant_id == tenant_id,
            )
            .first()
        )

    def list(
        self,
        db: Session,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        start_date: date | None = None,
        end_date: date | None = None,
        client_id: int | None = None,
    ) -> list[Sale]:
        from app.utils.timezone import get_date_range_bounds_brazil

        q = (
            db.query(Sale)
            .options(*_sale_eager_options())
            .filter(Sale.tenant_id == tenant_id)
        )
        if start_date or end_date:
            start_dt, end_dt = get_date_range_bounds_brazil(start_date, end_date)
            if start_dt:
                q = q.filter(Sale.created_at >= start_dt)
            if end_dt:
                q = q.filter(Sale.created_at <= end_dt)
        if client_id:
            q = q.filter(Sale.client_id == client_id)
        return q.order_by(desc(Sale.created_at)).offset(skip).limit(limit).all()

    def update_status(self, db: Session, tenant_id: int, sale_id: int, status: str) -> Sale | None:
        db_sale = self.get(db, tenant_id, sale_id)
        if db_sale:
            db_sale.status = status
            db.commit()
            db.refresh(db_sale)
            return db_sale
        return None

    # ── Comandas ────────────────────────────────────────────────────────────

    def save_open_comanda(self, db: Session, tenant_id: int, data: ComandaSaveRequest, user_id: int | None = None) -> Comanda:
        items_subtotal = sum(item.subtotal for item in data.items)
        calc_total = max(0.0, float(Decimal(str(items_subtotal)) - Decimal(str(data.discount_amount))))

        comanda = None
        if data.comanda_id:
            comanda = db.query(Comanda).filter(
                Comanda.id == data.comanda_id,
                Comanda.tenant_id == tenant_id,
            ).first()

        if not comanda and data.client_id:
            comanda = db.query(Comanda).filter(
                Comanda.client_id == data.client_id,
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
            ).first()

        if not comanda and data.appointment_id:
            comanda = db.query(Comanda).filter(
                Comanda.appointment_id == data.appointment_id,
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
            ).first()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        removed_appointment_services: list[tuple[int, int, list[int] | None]] = []

        if not comanda:
            comanda = Comanda(
                tenant_id=tenant_id,
                client_id=data.client_id,
                appointment_id=data.appointment_id,
                status="open",
                total_amount=calc_total,
                discount_amount=data.discount_amount,
                notes=data.notes,
            )
            db.add(comanda)
            db.flush()
        else:
            comanda.status = "open"
            comanda.client_id = data.client_id
            if data.appointment_id:
                comanda.appointment_id = data.appointment_id
            comanda.total_amount = calc_total
            comanda.discount_amount = data.discount_amount
            if data.notes is not None:
                comanda.notes = data.notes

            # Detect removed items among existing active items
            incoming_keys = {
                (
                    item.item_type,
                    item.item_id,
                    getattr(item, "appointment_id", None) or comanda.appointment_id or data.appointment_id if item.item_type == "service" else None,
                )
                for item in data.items
            }

            for existing_item in list(comanda.items):
                if getattr(existing_item, "status", "active") == "active":
                    apt_id = existing_item.appointment_id or comanda.appointment_id
                    key = (existing_item.item_type, existing_item.item_id, apt_id if existing_item.item_type == "service" else None)
                    if key not in incoming_keys:
                        existing_item.status = "removed"
                        existing_item.removed_at = now
                        existing_item.removed_by_user_id = user_id
                        existing_item.removal_reason = "Removido no carrinho/comanda do PDV"
                        db.add(existing_item)
                        if existing_item.item_type == "service" and apt_id:
                            removed_appointment_services.append((apt_id, existing_item.item_id, existing_item.pet_ids))

        if removed_appointment_services:
            self._sync_removed_services_from_appointments(db, tenant_id, removed_appointment_services, user_id=user_id)

        if len(data.items) == 0:
            if comanda and comanda.id:
                comanda.status = "canceled"
                comanda.total_amount = 0.0
                for ci in comanda.items:
                    if getattr(ci, "status", "active") == "active":
                        ci.status = "removed"
                        ci.removed_at = now
                        ci.removed_by_user_id = user_id
                        ci.removal_reason = "Comanda esvaziada no PDV"
                        db.add(ci)
                db.commit()
            return comanda

        # Add new items or update existing active items
        for item in data.items:
            apt_id = (getattr(item, "appointment_id", None) or comanda.appointment_id) if item.item_type == "service" else None
            existing = next(
                (
                    ci for ci in comanda.items
                    if getattr(ci, "status", "active") == "active"
                    and ci.item_type == item.item_type
                    and ci.item_id == item.item_id
                    and (ci.appointment_id == apt_id or (not ci.appointment_id and not apt_id))
                ),
                None
            )
            if existing:
                existing.name = item.name
                existing.quantity = item.quantity
                existing.unit_price = item.unit_price
                existing.subtotal = item.subtotal
                existing.employee_id = item.employee_id
                existing.pet_ids = item.pet_ids
                existing.client_package_id_to_pay = item.client_package_id_to_pay
                existing.unit = item.unit or "UN"
                db.add(existing)
            else:
                c_item = ComandaItem(
                    comanda_id=comanda.id,
                    item_type=item.item_type,
                    item_id=item.item_id,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    subtotal=item.subtotal,
                    employee_id=item.employee_id,
                    pet_ids=item.pet_ids,
                    client_package_id_to_pay=item.client_package_id_to_pay,
                    unit=item.unit or "UN",
                    appointment_id=apt_id,
                    status="active",
                )
                db.add(c_item)

        db.commit()
        return self.get_comanda(db, tenant_id, comanda.id)

    def _sync_removed_services_from_appointments(
        self,
        db: Session,
        tenant_id: int,
        removed_items: list[tuple[int, int, list[int] | None]],
        user_id: int | None = None,
    ):
        """
        When an uncovered service originating from an appointment is deleted from an open comanda,
        mark it as 'removed' (unbilled) in appointment_item_services and register an audit log,
        preserving history and the pet record while clearing pending payment status.
        """
        from datetime import datetime, timezone
        from app.modules.appointments.models import Appointment, AppointmentItem, AppointmentItemService, AppointmentAuditLog

        now = datetime.now(timezone.utc)

        for apt_id, service_id, pet_ids in removed_items:
            if not apt_id:
                continue
            appointment = db.query(Appointment).options(
                selectinload(Appointment.items).selectinload(AppointmentItem.services),
                selectinload(Appointment.items).selectinload(AppointmentItem.coverages),
                selectinload(Appointment.items).selectinload(AppointmentItem.pet),
            ).filter(
                Appointment.id == apt_id,
                Appointment.tenant_id == tenant_id,
            ).first()

            if not appointment or appointment.is_paid:
                continue

            for item in list(appointment.items):
                if pet_ids and item.pet_id not in pet_ids:
                    continue

                # Never touch a service that was covered by a package
                if any(c.service_id == service_id for c in item.coverages):
                    continue

                if any(s.id == service_id for s in item.services):
                    ais = db.query(AppointmentItemService).filter(
                        AppointmentItemService.appointment_item_id == item.id,
                        AppointmentItemService.service_id == service_id,
                    ).first()

                    service_obj = next((s for s in item.services if s.id == service_id), None)
                    service_name = service_obj.name if service_obj else None

                    if ais:
                        ais.status = "removed"
                        ais.removed_at = now
                        ais.removed_by_user_id = user_id
                        ais.removal_reason = "Removido no carrinho/comanda do PDV"
                        db.add(ais)
                    else:
                        ais = AppointmentItemService(
                            appointment_item_id=item.id,
                            service_id=service_id,
                            status="removed",
                            removed_at=now,
                            removed_by_user_id=user_id,
                            removal_reason="Removido no carrinho/comanda do PDV",
                        )
                        db.add(ais)

                    # Create immutable audit log
                    audit = AppointmentAuditLog(
                        tenant_id=tenant_id,
                        appointment_id=appointment.id,
                        appointment_item_id=item.id,
                        service_id=service_id,
                        service_name=service_name,
                        pet_id=item.pet_id,
                        pet_name=item.pet.name if item.pet else None,
                        user_id=user_id,
                        action="service_removed_from_pos",
                        notes=f"Serviço '{service_name}' removido da cobrança no PDV",
                    )
                    db.add(audit)

            db.flush()

    def get_comanda(self, db: Session, tenant_id: int, comanda_id: int) -> Comanda | None:
        return db.query(Comanda).options(
            selectinload(Comanda.client).selectinload(Client.pets),
            selectinload(Comanda.items).selectinload(ComandaItem.appointment),
            selectinload(Comanda.appointment),
        ).filter(
            Comanda.id == comanda_id,
            Comanda.tenant_id == tenant_id,
        ).first()

    def get_client_open_comanda(self, db: Session, tenant_id: int, client_id: int) -> Comanda | None:
        return db.query(Comanda).options(
            selectinload(Comanda.client).selectinload(Client.pets),
            selectinload(Comanda.items).selectinload(ComandaItem.appointment),
            selectinload(Comanda.appointment),
        ).filter(
            Comanda.client_id == client_id,
            Comanda.tenant_id == tenant_id,
            Comanda.status == "open",
            Comanda.items.any(),
        ).order_by(desc(Comanda.updated_at)).first()

    def list_open_comandas(
        self,
        db: Session,
        tenant_id: int,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Comanda], int]:
        q = db.query(Comanda).options(
            selectinload(Comanda.client).selectinload(Client.pets),
            selectinload(Comanda.items).selectinload(ComandaItem.appointment),
            selectinload(Comanda.appointment),
        ).join(Client, Comanda.client_id == Client.id).filter(
            Comanda.tenant_id == tenant_id,
            Comanda.status == "open",
            Comanda.items.any(ComandaItem.status == "active"),
        )

        if search:
            search_term = f"%{search}%"
            q = q.filter(
                or_(
                    Client.name.ilike(search_term),
                    Comanda.notes.ilike(search_term),
                )
            )

        total = q.count()
        items = q.order_by(desc(Comanda.updated_at)).offset(offset).limit(limit).all()
        return items, total

    def delete_comanda(self, db: Session, tenant_id: int, comanda_id: int, user_id: int | None = None) -> bool:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        comanda = self.get_comanda(db, tenant_id, comanda_id)
        if comanda and comanda.status == "open":
            removed_appointment_services: list[tuple[int, int, list[int] | None]] = []
            for existing_item in comanda.items:
                if getattr(existing_item, "status", "active") == "active":
                    existing_item.status = "removed"
                    existing_item.removed_at = now
                    existing_item.removed_by_user_id = user_id
                    existing_item.removal_reason = "Comanda cancelada/excluída no PDV"
                    db.add(existing_item)
                    apt_id = existing_item.appointment_id or comanda.appointment_id
                    if existing_item.item_type == "service" and apt_id:
                        removed_appointment_services.append((apt_id, existing_item.item_id, existing_item.pet_ids))

            comanda.status = "canceled"
            comanda.total_amount = 0.0
            if removed_appointment_services:
                self._sync_removed_services_from_appointments(db, tenant_id, removed_appointment_services, user_id=user_id)
            db.commit()
            return True
        return False
