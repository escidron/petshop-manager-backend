from fastapi import HTTPException

from app.modules.tenant_services.constants import DEFAULT_SERVICES
from app.modules.tenant_services.schemas import ServiceCreate

from .repository import ServiceRepository

class ServiceService:
    def __init__(self):
        self.repo = ServiceRepository()

    def create(self, db, tenant_id, data: ServiceCreate):
        # Validar duplicidade
        existing = self.repo.get_by_attributes(
            db,
            tenant_id=tenant_id,
            name=data.name,
            species=data.species,
            size=data.size,
            coat_type=data.coat_type
        )
        if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Já existe um serviço com este nome e as mesmas variações (Espécie, Porte, Pelagem). Para preços diferentes, especifique as variações correspondentes."
                )
            
        return self.repo.create(db, tenant_id, data)

    def list(self, db, tenant_id):
        return self.repo.list(db, tenant_id)

    def get(self, db, tenant_id, service_id):
        service = self.repo.get_by_id(
            db, tenant_id, service_id
        )
        if not service:
            raise HTTPException(404, "Serviço não encontrado")
        return service

    def update(self, db, tenant_id, service_id, data):
        service = self.get(db, tenant_id, service_id)
        
        # Se algum campo identificador mudar, validar duplicidade
        if any(v is not None for v in [data.name, data.species, data.size, data.coat_type]):
            new_name = data.name if data.name is not None else service.name
            new_species = data.species if data.species is not None else service.species
            new_size = data.size if data.size is not None else service.size
            new_coat = data.coat_type if data.coat_type is not None else service.coat_type
            
            existing = self.repo.get_by_attributes(
                db,
                tenant_id=tenant_id,
                name=new_name,
                species=new_species,
                size=new_size,
                coat_type=new_coat
            )
            
            if existing and existing.id != service_id:
                raise HTTPException(
                    status_code=400,
                    detail="Já existe um serviço cadastrado com este nome e variações."
                )

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