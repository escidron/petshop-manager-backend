from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .repository import ClientRepository
from .schemas import ClientCreate, ClientUpdate


class ClientService:
    def __init__(self):
        self.repository = ClientRepository()

    def create_client(
        self, db: Session, tenant_id: int, data: ClientCreate
    ):
        return self.repository.create(db, tenant_id, data)

    def get_client(
        self, db: Session, tenant_id: int, client_id: int
    ):
        client = self.repository.get_by_id(
            db, tenant_id, client_id
        )
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )
        return client

    def list_clients(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def update_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        data: ClientUpdate,
    ):
        client = self.get_client(db, tenant_id, client_id)
        return self.repository.update(db, client, data)

    def delete_client(
        self, db: Session, tenant_id: int, client_id: int
    ):
        client = self.get_client(db, tenant_id, client_id)
        self.repository.delete(db, client)
