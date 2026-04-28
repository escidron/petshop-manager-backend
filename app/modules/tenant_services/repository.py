from sqlalchemy.orm import Session
from .models import Service
from .schemas import ServiceCreate, ServiceUpdate


class ServiceRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        data: ServiceCreate,
    ) -> Service:
        service = Service(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def list(
        self,
        db: Session,
        tenant_id: int,
    ) -> list[Service]:
        return (
            db.query(Service)
            .filter(Service.tenant_id == tenant_id)
            .order_by(Service.name)
            .all()
        )

    def get_by_id(
        self,
        db: Session,
        tenant_id: int,
        service_id: int,
    ) -> Service | None:
        return (
            db.query(Service)
            .filter(
                Service.id == service_id,
                Service.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_attributes(
        self,
        db: Session,
        tenant_id: int,
        name: str,
        species: str | None = None,
        size: str | None = None,
        coat_type: str | None = None,
    ) -> Service | None:
        return (
            db.query(Service)
            .filter(
                Service.tenant_id == tenant_id,
                Service.name == name,
                Service.species == species,
                Service.size == size,
                Service.coat_type == coat_type,
            )
            .first()
        )

    def update(
        self,
        db: Session,
        service: Service,
        data: ServiceUpdate,
    ) -> Service:
        for field, value in data.model_dump(
            exclude_unset=True
        ).items():
            setattr(service, field, value)

        db.commit()
        db.refresh(service)
        return service

    def delete(self, db: Session, service: Service):
        db.delete(service)
        db.commit()
