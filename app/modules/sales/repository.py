from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc, func, or_

from .models import Sale, SaleItem, Comanda, ComandaItem
from .schemas import SaleCreate, ComandaSaveRequest
from app.modules.clients.models import Client


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
            )
            db.add(db_item)

        # If linked to a comanda (or if an open comanda exists for this appointment/client), mark it completed
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

        if target_comanda:
            target_comanda.status = "completed"
            db.add(target_comanda)

        db.commit()
        db.refresh(db_sale)
        return db_sale

    def get(self, db: Session, tenant_id: int, sale_id: int) -> Sale | None:
        return db.query(Sale).filter(
            Sale.id == sale_id,
            Sale.tenant_id == tenant_id,
        ).first()

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
        q = db.query(Sale).filter(Sale.tenant_id == tenant_id)
        if start_date:
            q = q.filter(Sale.created_at >= datetime.combine(start_date, time.min))
        if end_date:
            q = q.filter(Sale.created_at <= datetime.combine(end_date, time.max))
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

    def save_open_comanda(self, db: Session, tenant_id: int, data: ComandaSaveRequest) -> Comanda:
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
            # Clear old items to rebuild
            comanda.items.clear()
            db.flush()

        for item in data.items:
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
            )
            db.add(c_item)

        db.commit()
        db.refresh(comanda)
        return comanda

    def get_comanda(self, db: Session, tenant_id: int, comanda_id: int) -> Comanda | None:
        return db.query(Comanda).options(
            selectinload(Comanda.client).selectinload(Client.pets),
            selectinload(Comanda.items),
        ).filter(
            Comanda.id == comanda_id,
            Comanda.tenant_id == tenant_id,
        ).first()

    def get_client_open_comanda(self, db: Session, tenant_id: int, client_id: int) -> Comanda | None:
        return db.query(Comanda).options(
            selectinload(Comanda.client).selectinload(Client.pets),
            selectinload(Comanda.items),
        ).filter(
            Comanda.client_id == client_id,
            Comanda.tenant_id == tenant_id,
            Comanda.status == "open",
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
            selectinload(Comanda.items),
        ).join(Client, Comanda.client_id == Client.id).filter(
            Comanda.tenant_id == tenant_id,
            Comanda.status == "open",
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

    def delete_comanda(self, db: Session, tenant_id: int, comanda_id: int) -> bool:
        comanda = self.get_comanda(db, tenant_id, comanda_id)
        if comanda and comanda.status == "open":
            db.delete(comanda)
            db.commit()
            return True
        return False
