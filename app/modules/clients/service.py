from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .repository import ClienteRepository
from .schemas import ClienteCreate, ClienteUpdate


class ClienteService:
    def __init__(self):
        self.repository = ClienteRepository()

    def create_cliente(
        self, db: Session, tenant_id: int, data: ClienteCreate
    ):
        return self.repository.create(db, tenant_id, data)

    def get_cliente(
        self, db: Session, tenant_id: int, cliente_id: int
    ):
        cliente = self.repository.get_by_id(
            db, tenant_id, cliente_id
        )
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )
        return cliente

    def list_clientes(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def update_cliente(
        self,
        db: Session,
        tenant_id: int,
        cliente_id: int,
        data: ClienteUpdate,
    ):
        cliente = self.get_cliente(db, tenant_id, cliente_id)
        return self.repository.update(db, cliente, data)

    def delete_cliente(
        self, db: Session, tenant_id: int, cliente_id: int
    ):
        cliente = self.get_cliente(db, tenant_id, cliente_id)
        self.repository.delete(db, cliente)
