from sqlalchemy.orm import Session, joinedload
from .models import Package, PackageItem
from .schemas import PackageCreate, PackageUpdate, PackageItemCreate

class PackageRepository:
    def create(self, db: Session, tenant_id: int, data: PackageCreate) -> Package:
        package = Package(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            price_cents=data.price_cents,
            is_active=data.is_active,
        )
        db.add(package)
        db.flush()  # To get package.id

        for item_data in data.items:
            item = PackageItem(
                package_id=package.id,
                service_id=item_data.service_id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
            )
            db.add(item)
        
        db.commit()
        db.refresh(package)
        return package

    def get_by_id(self, db: Session, tenant_id: int, package_id: int) -> Package | None:
        return (
            db.query(Package)
            .options(
                joinedload(Package.items).joinedload(PackageItem.service),
                joinedload(Package.items).joinedload(PackageItem.product),
            )
            .filter(
                Package.id == package_id,
                Package.tenant_id == tenant_id,
            )
            .first()
        )

    def list(self, db: Session, tenant_id: int) -> list[Package]:
        return (
            db.query(Package)
            .options(
                joinedload(Package.items).joinedload(PackageItem.service),
                joinedload(Package.items).joinedload(PackageItem.product),
            )
            .filter(Package.tenant_id == tenant_id)
            .order_by(Package.name)
            .all()
        )

    def update(self, db: Session, package: Package, data: PackageUpdate) -> Package:
        update_data = data.model_dump(exclude_unset=True)
        items_data = update_data.pop("items", None)

        for field, value in update_data.items():
            setattr(package, field, value)

        if items_data is not None:
            # Simple approach: Replace items
            db.query(PackageItem).filter(PackageItem.package_id == package.id).delete()
            for item_data in items_data:
                item = PackageItem(
                    package_id=package.id,
                    service_id=item_data.get("service_id"),
                    product_id=item_data.get("product_id"),
                    quantity=item_data.get("quantity", 1),
                )
                db.add(item)

        db.commit()
        db.refresh(package)
        return package

    def delete(self, db: Session, package: Package) -> None:
        db.delete(package)
        db.commit()
