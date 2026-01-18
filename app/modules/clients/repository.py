from sqlalchemy.orm import Session
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
