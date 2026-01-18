from sqlalchemy.orm import Session
from app.modules.clients.models import Client
from app.modules.clients.schemas import ClienteCreate, ClienteUpdate


class ClienteRepository:
    def create(self, db: Session, tenant_id: int, data: ClienteCreate) -> Client:
        cliente = Client(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        return cliente

    def get_by_id(
        self, db: Session, tenant_id: int, cliente_id: int
    ) -> Client | None:
        return (
            db.query(Client)
            .filter(
                Client.id == cliente_id,
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
        cliente: Client,
        data: ClienteUpdate,
    ) -> Client:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(cliente, field, value)

        db.commit()
        db.refresh(cliente)
        return cliente

    def delete(self, db: Session, cliente: Client) -> None:
        db.delete(cliente)
        db.commit()
