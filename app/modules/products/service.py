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

    def list_products(self, db: Session, tenant_id: int, exclude_internal: bool = False):
        return self.repository.list(db, tenant_id, exclude_internal=exclude_internal)

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
        return product    async def import_products_from_excel(self, db: Session, tenant_id: int, file_content: bytes):
        import openpyxl
        
        if not file_content:
            return {"imported": 0, "errors": ["Arquivo de planilha vazio"]}

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
            ws = wb.active
        except Exception as e:
            return {"imported": 0, "errors": [f"Erro ao ler arquivo Excel: {str(e)}"]}

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"imported": 0, "errors": ["A planilha está vazia"]}

        # Headers are in the first row
        raw_headers = rows[0]
        # Clean headers
        headers = []
        for h in raw_headers:
            if h is None:
                headers.append("")
            else:
                headers.append(str(h).strip().lower().replace("*", "").strip())

        required_cols = ["nome", "preco_venda"]
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols:
            return {
                "imported": 0,
                "errors": [f"Colunas obrigatórias ausentes na planilha: {', '.join(missing_cols)}"]
            }

        imported_count = 0
        errors = []

        # Helper to parse prices/costs robustly
        def parse_money(val):
            if val is None or str(val).strip() == "":
                return None
            
            # If Excel has already parsed it as float or int, multiply by 100
            if isinstance(val, (int, float)):
                return int(round(val * 100))
                
            try:
                # Remove R$, whitespace, and dots used as thousand separators
                cleaned = str(val).replace("R$", "").strip()
                
                if "," in cleaned and "." in cleaned:
                    if cleaned.rfind(",") > cleaned.rfind("."):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        cleaned = cleaned.replace(",", "")
                elif "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                
                return int(round(float(cleaned) * 100))
            except (ValueError, TypeError):
                return None

        # Process each row, skipping header (row_idx start=2 for standard 1-based index representation)
        for row_idx, row_values in enumerate(rows[1:], start=2):
            try:
                # Build dict mapping cleaned header to cell value
                row = {}
                has_any_value = False
                for h, val in zip(headers, row_values):
                    if h: # Ignore empty/unnamed columns
                        row[h] = val
                        if val is not None and str(val).strip() != "":
                            has_any_value = True
                
                if not has_any_value:
                    continue

                # Basic validation: Name is strictly required
                name = row.get("nome")
                if name is None or str(name).strip() == "":
                    raise ValueError("Nome do produto é obrigatório")
                name = str(name).strip()
                
                # Price is strictly required
                raw_price = row.get("preco_venda")
                price = parse_money(raw_price)
                if price is None:
                    raise ValueError("Preço de venda é obrigatório e deve ser um valor válido")
                
                # Cost is optional
                raw_cost = row.get("custo")
                cost = parse_money(raw_cost) if raw_cost is not None else None

                # Clean optional barcode, ncm, etc to string
                def clean_str(val):
                    if val is None or str(val).strip() == "":
                        return None
                    # If Excel parses standard numeric SKU/Barcode/NCM as float/int, avoid trailing .0
                    if isinstance(val, float) and val.is_integer():
                        return str(int(val))
                    return str(val).strip()

                # Parse unit of measure mapping descriptive names back to code
                def parse_unit(val):
                    if val is None or str(val).strip() == "":
                        raise ValueError("Unidade de medida é obrigatória")
                    cleaned = str(val).strip().lower()
                    unit_map = {
                        "unidade (un)": "UN",
                        "grama (g)": "g",
                        "quilograma (kg)": "kg",
                        "mililitro (ml)": "ml",
                        "litro (l)": "L",
                        "pacote (paq)": "PAQ",
                        "caixa (cx)": "CX",
                        # Direct abbreviations fallback
                        "un": "UN",
                        "g": "g",
                        "kg": "kg",
                        "ml": "ml",
                        "l": "L",
                        "paq": "PAQ",
                        "cx": "CX"
                    }
                    if cleaned not in unit_map:
                         raise ValueError(f"Unidade de medida inválida: {val}")
                    return unit_map[cleaned]

                barcode = clean_str(row.get("codigo_barras"))
                if not barcode:
                    raise ValueError("Código de barras é obrigatório")
                    
                ncm = clean_str(row.get("ncm"))
                if not ncm:
                    raise ValueError("NCM é obrigatório")

                try:
                    quantity = int(row.get("quantidade") or 0)
                except (ValueError, TypeError):
                    quantity = 0

                try:
                    min_stock = int(row.get("estoque_minimo") or 0)
                except (ValueError, TypeError):
                    min_stock = 0

                data = ProductCreate(
                    name=name,
                    sku=clean_str(row.get("sku")),
                    description=clean_str(row.get("descricao")),
                    category=clean_str(row.get("categoria")),
                    price=float(price),
                    cost=float(cost) if cost is not None else None,
                    quantity=quantity,
                    min_stock=min_stock,
                    barcode=barcode,
                    ncm=ncm,
                    cest=clean_str(row.get("cest")),
                    cfop=clean_str(row.get("cfop")),
                    csosn=clean_str(row.get("csosn")),
                    cst_pis=clean_str(row.get("cst_pis")),
                    cst_cofins=clean_str(row.get("cst_cofins")),
                    unit=parse_unit(row.get("unidade")),
                )
                self.repository.create(db, tenant_id, data)
                imported_count += 1
            except Exception as e:
                errors.append(f"Linha {row_idx}: {str(e)}")

        return {"imported": imported_count, "errors": errors}

    def generate_import_template_excel(self) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.datavalidation import DataValidation
        from io import BytesIO
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Produtos"
        
        # Add headers
        headers = [
            "nome *", "preco_venda *", "unidade *", "quantidade *", "estoque_minimo *", "codigo_barras *", "ncm *",
            "sku", "descricao", "categoria", "custo", 
            "cest", "cfop", "csosn", "cst_pis", "cst_cofins"
        ]
        ws.append(headers)
        
        # Style headers (Segoe UI, Blue color theme)
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
        required_header_fill = PatternFill(start_color="D32F2F", end_color="D32F2F", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center")
        
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3")
        )
        
        # Format header row
        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            header_name = headers[col_idx - 1]
            if "*" in header_name:
                cell.fill = required_header_fill
            else:
                cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border
            
        # Add example row
        example = [
            "Ração Premium Gato Adulto 1kg",
            89.90,
            "Unidade (UN)",
            20,
            5,
            "7891234567890",
            "3801.10.00",
            "RAC-PREM-GAT-1",
            "Ração premium para gatos adultos sabor salmão",
            "Ração",
            45.00,
            "01.001.00",
            "5102",
            "102",
            "01",
            "01"
        ]
        ws.append(example)
        
        # Format example row (row 2)
        ws.row_dimensions[2].height = 20
        for col_idx in range(1, len(example) + 1):
            cell = ws.cell(row=2, column=col_idx)
            cell.font = Font(name="Segoe UI", size=10)
            cell.border = thin_border
            
            # Alignments & formatting based on content
            if col_idx in [1, 4, 5]: # Text
                cell.alignment = left_align
            else: # Numbers / Codes / Selects
                cell.alignment = center_align
                
            # Number formats
            if col_idx in [2, 7]: # currency
                cell.number_format = "#,##0.00"
            elif col_idx in [8, 9]: # integer
                cell.number_format = "#,##0"
                
        # Data Validations (Dropdowns)
        # 1. Units (Column C - col_idx 3)
        dv_unit = DataValidation(type="list", formula1='"Unidade (UN),Grama (g),Quilograma (kg),Mililitro (ml),Litro (L),Pacote (PAQ),Caixa (CX)"', allow_blank=True)
        dv_unit.error = 'Escolha uma unidade da lista'
        dv_unit.errorTitle = 'Unidade Inválida'
        dv_unit.prompt = 'Selecione a unidade de medida do produto'
        dv_unit.promptTitle = 'Unidade de Medida'
        ws.add_data_validation(dv_unit)
        dv_unit.add("C2:C1000")
        
        # 2. Categories (Column F - col_idx 6)
        categories_list = "Ração,Acessórios,Higiene,Brinquedos,Medicamentos,Petiscos,Camas e Casinhas,Roupas,Aquarismo,Aves,Outros"
        dv_category = DataValidation(type="list", formula1=f'"{categories_list}"', allow_blank=True)
        dv_category.error = 'Escolha uma categoria da lista'
        dv_category.errorTitle = 'Categoria Inválida'
        dv_category.prompt = 'Selecione a categoria do produto'
        dv_category.promptTitle = 'Categoria'
        ws.add_data_validation(dv_category)
        dv_category.add("F2:F1000")
                
        # Auto-fit column widths
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
        # Enable grid lines explicitly
        ws.views.sheetView[0].showGridLines = True
            
        out = BytesIO()
        wb.save(out)
        return out.getvalue()

