from datetime import date, datetime, time
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.modules.clients.models import Client
from app.modules.clients.schemas import ClientCreate, ClientUpdate


class ClientRepository:
    def create(self, db: Session, tenant_id: int, data: ClientCreate) -> Client:
        client = Client(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return client

    def get_by_id(
        self, db: Session, tenant_id: int, client_id: int
    ) -> Client | None:
        return (
            db.query(Client)
            .filter(
                Client.id == client_id,
                Client.tenant_id == tenant_id,
            )
            .first()
        )

    def list(
        self, db: Session, tenant_id: int
    ) -> list[Client]:
        return (
            db.query(Client)
            .options(joinedload(Client.pets))
            .filter(Client.tenant_id == tenant_id)
            .order_by(Client.name)
            .all()
        )

    def update(
        self,
        db: Session,
        client: Client,
        data: ClientUpdate,
    ) -> Client:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(client, field, value)

        db.commit()
        db.refresh(client)
        return client

    def delete(self, db: Session, client: Client) -> None:
        db.delete(client)
        db.commit()

    def count_new_clients(
        self,
        db: Session,
        tenant_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        q = db.query(func.count(Client.id)).filter(Client.tenant_id == tenant_id)
        if start_date or end_date:
            from app.utils.timezone import get_date_range_bounds_brazil
            start_dt, end_dt = get_date_range_bounds_brazil(start_date, end_date)
            if start_dt:
                q = q.filter(Client.created_at >= start_dt)
            if end_dt:
                q = q.filter(Client.created_at <= end_dt)
        return q.scalar() or 0
