from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from .repository import PackageRepository
from .schemas import PackageCreate, PackageUpdate

class PackageService:
    def __init__(self):
        self.repository = PackageRepository()

    def create_package(self, db: Session, tenant_id: int, data: PackageCreate):
        return self.repository.create(db, tenant_id, data)

    def list_packages(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def get_package(self, db: Session, tenant_id: int, package_id: int):
        package = self.repository.get_by_id(db, tenant_id, package_id)
        if not package:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Package not found",
            )
        return package

    def update_package(self, db: Session, tenant_id: int, package_id: int, data: PackageUpdate):
        package = self.get_package(db, tenant_id, package_id)
        return self.repository.update(db, package, data)

    def delete_package(self, db: Session, tenant_id: int, package_id: int):
        package = self.get_package(db, tenant_id, package_id)
        self.repository.delete(db, package)
