from sqlalchemy.orm import Session, joinedload
from app.modules.products.models import Product
from app.modules.products.schemas import ProductCreate, ProductUpdate


class ProductRepository:
    def create(self, db: Session, tenant_id: int, data: ProductCreate) -> Product:
        product = Product(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    def get_by_id(self, db: Session, tenant_id: int, product_id: int) -> Product | None:
        return (
            db.query(Product)
            .options(joinedload(Product.photos))
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

    def list(self, db: Session, tenant_id: int, exclude_internal: bool = False) -> list[Product]:
        query = db.query(Product).options(joinedload(Product.photos)).filter(Product.tenant_id == tenant_id)
        if exclude_internal:
            query = query.filter(Product.is_internal_use == False)
        return query.order_by(Product.name).all()

    def update(self, db: Session, product: Product, data: ProductUpdate) -> Product:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(product, field, value)

        db.commit()
        db.refresh(product)
        return product

    def delete(self, db: Session, product: Product) -> None:
        db.delete(product)
        db.commit()
