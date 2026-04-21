import csv
import io
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from .repository import ProductRepository
from .inventory_repository import InventoryRepository
from .schemas import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self):
        self.repository = ProductRepository()
        self.inventory_repository = InventoryRepository()

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

    def adjust_stock(
        self, 
        db: Session, 
        tenant_id: int, 
        product_id: int, 
        quantity_change: int, 
        change_type: str, 
        notes: str | None = None
    ):
        product = self.get_product(db, tenant_id, product_id)
        product.quantity += quantity_change
        
        self.inventory_repository.create_log(
            db, tenant_id, product_id, quantity_change, change_type, notes
        )
        db.commit()
    async def import_products_from_csv(self, db: Session, tenant_id: int, csv_content: str):
        f = io.StringIO(csv_content)
        # We try to detect the delimiter (comma or semicolon are common in Brazil)
        # But we'll stick to comma for the base template
        reader = csv.DictReader(f)
        
        imported_count = 0
        errors = []
        
        for row_idx, row in enumerate(reader, start=2):
            try:
                # Handle potential empty rows
                if not any(row.values()):
                    continue
                    
                # Basic validation: Name and Price are strictly required
                name = row.get("nome")
                if not name:
                    raise ValueError("Nome do produto é obrigatório")
                
                price_str = row.get("preco_venda", "0").replace(",", ".")
                try:
                    # Convert to cents as the system expects integer-like values in the price field
                    price = int(float(price_str) * 100)
                except ValueError:
                    raise ValueError(f"Preço de venda inválido: {price_str}")

                data = ProductCreate(
                    name=name,
                    sku=row.get("sku") or None,
                    description=row.get("descricao") or None,
                    category=row.get("categoria") or None,
                    price=price,
                    cost=int(float(row.get("custo").replace(",", ".")) * 100) if row.get("custo") else None,
                    quantity=int(row.get("quantidade") or 0),
                    min_stock=max(1, int(row.get("estoque_minimo") or 1)),
                    barcode=row.get("codigo_barras") or None,
                    ncm=row.get("ncm") or None,
                    cest=row.get("cest") or None,
                    cfop=row.get("cfop") or None,
                    csosn=row.get("csosn") or None,
                    cst_pis=row.get("cst_pis") or None,
                    cst_cofins=row.get("cst_cofins") or None,
                )
                self.repository.create(db, tenant_id, data)
                imported_count += 1
            except Exception as e:
                errors.append(f"Linha {row_idx}: {str(e)}")
        
        return {"imported": imported_count, "errors": errors}
