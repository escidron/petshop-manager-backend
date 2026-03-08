from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from .repository import ProductRepository
from .schemas import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self):
        self.repository = ProductRepository()

    def create_product(self, db: Session, tenant_id: int, data: ProductCreate):
        return self.repository.create(db, tenant_id, data)

    def get_product(self, db: Session, tenant_id: int, product_id: int):
        product = self.repository.get_by_id(db, tenant_id, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado",
            )
        return product

    def list_products(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def update_product(self, db: Session, tenant_id: int, product_id: int, data: ProductUpdate):
        product = self.get_product(db, tenant_id, product_id)
        return self.repository.update(db, product, data)

    def delete_product(self, db: Session, tenant_id: int, product_id: int):
        product = self.get_product(db, tenant_id, product_id)
        self.repository.delete(db, product)
