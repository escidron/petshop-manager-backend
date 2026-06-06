import sys
import os
import asyncio
import io
import openpyxl
from unittest.mock import MagicMock

# Add back-end to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.products.service import ProductService
from app.modules.products.schemas import ProductCreate

def create_excel_bytes(headers, data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(headers)
    for row in data_rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

async def run_test():
    service = ProductService()
    # Mock database and repository
    db = MagicMock()
    service.repository = MagicMock()
    service.repository.create.return_value = None
    
    tenant_id = 1
    
    print("=== TEST 1: Template Generation ===")
    template_bytes = service.generate_import_template_excel()
    assert len(template_bytes) > 0, "Template generation returned empty bytes"
    # Try loading it with openpyxl to check if it's a valid zip file/workbook
    wb_template = openpyxl.load_workbook(io.BytesIO(template_bytes))
    ws_template = wb_template.active
    print(f"Template loaded successfully! Title: {ws_template.title}")
    
    headers_in_template = [cell.value for cell in ws_template[1]]
    print(f"Template headers: {headers_in_template}")
    assert "nome *" in headers_in_template, "Header 'nome *' not found in template"
    assert "unidade" in headers_in_template, "Header 'unidade' not found in template"
    
    # Assert data validations exist
    validations = ws_template.data_validations.dataValidation
    print(f"Template data validations count: {len(validations)}")
    assert len(validations) >= 2, "Expected at least 2 data validations (units and categories)"
    print("Test 1 SUCCESS!")
    
    print("\n=== TEST 2: Import Standard Excel ===")
    headers = [
        "nome *", "preco_venda *", "unidade", "sku", "descricao", "categoria",
        "custo", "quantidade", "estoque_minimo", "codigo_barras"
    ]
    data_rows = [
        ["Ração Cão", 120.50, "Quilograma (kg)", "RAC-CAO-1", "Ração especial para cães", "Ração", 60.00, 15, 3, "7891234567890"],
        ["Coleira Azul", "R$ 29,90", "", "COL-AZU", "Coleira ajustável azul", "Acessórios", "12,50", 10, 1, 7891112223334],
        ["Ração Sachê", 10.00, "PAQ", "SAC-01", "Sachê ração", "Ração", 5.00, 30, 5, ""]
    ]
    
    excel_bytes = create_excel_bytes(headers, data_rows)
    result = await service.import_products_from_excel(db, tenant_id, excel_bytes)
    
    print(f"Result: {result}")
    assert result["imported"] == 3, f"Expected 3 products imported, got {result['imported']}"
    assert len(result["errors"]) == 0, f"Expected 0 errors, got {result['errors']}"
    
    # Check repository call args
    calls = service.repository.create.call_args_list
    assert len(calls) == 3, f"Expected 3 repository calls, got {len(calls)}"
    
    # Check first item details (descriptive unit option mapping)
    first_product = calls[0][0][2]
    print(f"Product 1 parsed: name={first_product.name}, price={first_product.price}, cost={first_product.cost}, quantity={first_product.quantity}, unit={first_product.unit}, barcode={first_product.barcode}")
    assert first_product.price == 12050, f"Expected 12050 cents, got {first_product.price}"
    assert first_product.cost == 6000, f"Expected 6000 cents, got {first_product.cost}"
    assert first_product.quantity == 15, f"Expected 15 quantity, got {first_product.quantity}"
    assert first_product.unit == "kg", f"Expected unit 'kg' mapped from 'Quilograma (kg)', got {first_product.unit}"
    assert first_product.barcode == "7891234567890", f"Expected barcode '7891234567890', got {first_product.barcode}"
    
    # Check second item details (unit should default to "UN" since it's empty in sheet)
    second_product = calls[1][0][2]
    print(f"Product 2 parsed: name={second_product.name}, price={second_product.price}, cost={second_product.cost}, quantity={second_product.quantity}, unit={second_product.unit}, barcode={second_product.barcode}")
    assert second_product.price == 2990, f"Expected 2990 cents, got {second_product.price}"
    assert second_product.cost == 1250, f"Expected 1250 cents, got {second_product.cost}"
    assert second_product.unit == "UN", f"Expected default unit 'UN', got {second_product.unit}"
    assert second_product.barcode == "7891112223334", f"Expected barcode '7891112223334', got {second_product.barcode}"

    # Check third item details (direct abbreviation fallback)
    third_product = calls[2][0][2]
    print(f"Product 3 parsed: name={third_product.name}, price={third_product.price}, cost={third_product.cost}, quantity={third_product.quantity}, unit={third_product.unit}, barcode={third_product.barcode}")
    assert third_product.price == 1000, f"Expected 1000 cents, got {third_product.price}"
    assert third_product.cost == 500, f"Expected 500 cents, got {third_product.cost}"
    assert third_product.unit == "PAQ", f"Expected unit 'PAQ' fallback, got {third_product.unit}"
    print("Test 2 SUCCESS!")
    
    print("\n=== TEST 3: Validation Failures ===")
    service.repository.create.reset_mock()
    # 1st row has missing name, 2nd row has missing price, 3rd row is valid
    bad_data_rows = [
        ["", 29.90, "BAD1"],
        ["Produto Sem Preço", "", "BAD2"],
        ["Produto Válido", 10.00, "GOOD"]
    ]
    bad_excel_bytes = create_excel_bytes(["nome *", "preco_venda *", "sku"], bad_data_rows)
    result_bad = await service.import_products_from_excel(db, tenant_id, bad_excel_bytes)
    print(f"Result (failures expected): {result_bad}")
    assert result_bad["imported"] == 1, f"Expected 1 import, got {result_bad['imported']}"
    assert len(result_bad["errors"]) == 2, f"Expected 2 errors, got {len(result_bad['errors'])}"
    assert "Linha 2" in result_bad["errors"][0], "Expected error in Row 2"
    assert "Linha 3" in result_bad["errors"][1], "Expected error in Row 3"
    print("Test 3 SUCCESS!")
    
    print("\n=== ALL TESTS SUCCESSFUL! ===")

if __name__ == "__main__":
    asyncio.run(run_test())
