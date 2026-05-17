import sys
import os
import asyncio
import io
import csv
from unittest.mock import MagicMock

# Add back-end to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.products.service import ProductService
from app.modules.products.schemas import ProductCreate

async def run_test():
    service = ProductService()
    # Mock repository
    service.repository = MagicMock()
    service.repository.create.return_value = None
    
    db = MagicMock()
    tenant_id = 1
    
    # Test cases
    test_cases = [
        {
            "name": "Standard CSV (Comma)",
            "content": "nome,preco_venda,quantidade\nProduto A,10.00,5"
        },
        {
            "name": "Brazilian Format (Semicolon and Comma)",
            "content": "nome;preco_venda;custo\nProduto B;29,90;15,00"
        },
        {
            "name": "Missing Required Header (preco_venda)",
            "content": "nome,quantidade\nProduto C,10"
        },
        {
            "name": "Missing Value in Row (name)",
            "content": "nome,preco_venda\n,10.00"
        },
        {
            "name": "Missing Value in Row (price)",
            "content": "nome,preco_venda\nProduto D,"
        },
        {
            "name": "Invalid Price Format",
            "content": "nome,preco_venda\nProduto E,invalid"
        }
    ]
    
    for case in test_cases:
        print(f"\nTesting: {case['name']}")
        result = await service.import_products_from_csv(db, tenant_id, case['content'])
        print(f"  Imported: {result['imported']}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  Error: {err}")
        
        # Verify repository calls if expected
        if case['name'] in ["Standard CSV (Comma)", "Brazilian Format (Semicolon and Comma)"]:
            if result['imported'] > 0:
                print(f"  SUCCESS: Imported {result['imported']} products.")
            else:
                print(f"  FAILURE: Should have imported products.")
        else:
            if result['imported'] == 0 or len(result['errors']) > 0:
                print(f"  SUCCESS: Correctly handled error.")
            else:
                print(f"  FAILURE: Should have reported error.")

if __name__ == "__main__":
    asyncio.run(run_test())
