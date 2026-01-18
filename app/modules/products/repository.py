from sqlalchemy.orm import Session
from app.modules.products.models import Product
from app.modules.products.schemas import (
    ProductCreate,
    ProductUpdate,
)


class ProductRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        data: ProductCreate,
    ) -> Product:
        product = Product(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    def get_by_id(
        self,
        db: Session,
        tenant_id: int,
        product_id: int,
    ) -> Product | None:
        return (
            db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

    def list(
        self,
        db: Session,
        tenant_id: int,
    ) -> list[Product]:
        return (
            db.query(Product)
            .filter(Product.tenant_id == tenant_id)
            .order_by(Product.name)
            .all()
        )

    def update(
        self,
        db: Session,
        product: Product,
        data: ProductUpdate,
    ) -> Product:
        for field, value in data.model_dump(
            exclude_unset=True
        ).items():
            setattr(product, field, value)

        db.commit()
        db.refresh(product)
        return product

    def delete(self, db: Session, product: Product):
        db.delete(product)
        db.commit()
