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
        db.refresh(product)
        return product
    async def import_products_from_csv(self, db: Session, tenant_id: int, csv_content: str):
        if not csv_content.strip():
            return {"imported": 0, "errors": ["Arquivo CSV está vazio"]}

        f = io.StringIO(csv_content)
        
        try:
            # Try to detect the delimiter (comma, semicolon, tab)
            sample = csv_content[:4096]
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
        except Exception:
            # Fallback to default if sniffer fails
            f.seek(0)
            reader = csv.DictReader(f)
        
        # Header validation
        fieldnames = [str(f).strip().lower() for f in (reader.fieldnames or [])]
        required_cols = ["nome", "preco_venda"]
        missing_cols = [col for col in required_cols if col not in fieldnames]
        
        if missing_cols:
            return {
                "imported": 0, 
                "errors": [f"Colunas obrigatórias ausentes no CSV: {', '.join(missing_cols)}"]
            }

        imported_count = 0
        errors = []
        
        # Helper to parse prices/costs robustly
        def parse_money(val_str):
            if not val_str or str(val_str).strip() == "": 
                return None
            try:
                # Remove R$, whitespace, and dots used as thousand separators
                # Brazilian format: 1.234,56 -> we want 1234.56
                # US format: 1,234.56 -> we want 1234.56
                cleaned = str(val_str).replace("R$", "").strip()
                
                # Check which one is the decimal separator
                if "," in cleaned and "." in cleaned:
                    # Mixed format: if comma comes after dot, it's Brazilian 1.234,56
                    if cleaned.rfind(",") > cleaned.rfind("."):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        # US format 1,234.56
                        cleaned = cleaned.replace(",", "")
                elif "," in cleaned:
                    # Only comma: probably decimal separator unless it's used as thousand separator
                    # In Brazil, 29,90 is common.
                    cleaned = cleaned.replace(",", ".")
                
                return int(float(cleaned) * 100)
            except (ValueError, TypeError):
                return None

        for row_idx, raw_row in enumerate(reader, start=2):
            try:
                # Clean row: strip whitespace from keys and values, handle casing
                row = {str(k).strip().lower(): str(v).strip() for k, v in raw_row.items() if k is not None}
                
                # Handle potential empty rows
                if not any(row.values()):
                    continue
                    
                # Basic validation: Name is strictly required
                name = row.get("nome")
                if not name:
                    raise ValueError("Nome do produto é obrigatório")
                
                # Price is strictly required
                raw_price = row.get("preco_venda")
                price = parse_money(raw_price)
                if price is None:
                    raise ValueError("Preço de venda é obrigatório e deve ser um valor válido")
                
                # Cost is optional
                raw_cost = row.get("custo")
                cost = parse_money(raw_cost) if raw_cost else None

                data = ProductCreate(
                    name=name,
                    sku=row.get("sku") or None,
                    description=row.get("descricao") or None,
                    category=row.get("categoria") or None,
                    price=float(price),
                    cost=float(cost) if cost is not None else None,
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
