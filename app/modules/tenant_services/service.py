from fastapi import HTTPException

from app.modules.tenant_services.constants import DEFAULT_SERVICES
from app.modules.tenant_services.schemas import ServiceCreate

from .repository import ServiceRepository

class ServiceService:
    def __init__(self):
        self.repo = ServiceRepository()

    def create(self, db, tenant_id, data):
        return self.repo.create(db, tenant_id, data)

    def list(self, db, tenant_id):
        return self.repo.list(db, tenant_id)

    def get(self, db, tenant_id, service_id):
        service = self.repo.get_by_id(
            db, tenant_id, service_id
        )
        if not service:
            raise HTTPException(404, "Service not found")
        return service

    def update(self, db, tenant_id, service_id, data):
        service = self.get(db, tenant_id, service_id)
        return self.repo.update(db, service, data)

    def delete(self, db, tenant_id, service_id):
        service = self.get(db, tenant_id, service_id)
        self.repo.delete(db, service)

    def create_default_services(
        self,
        db,
        tenant_id: int,
    ):
        for service in DEFAULT_SERVICES:
            data = ServiceCreate(**service)
            self.repo.create(
                db,
                tenant_id=tenant_id,
                data=data,
            )