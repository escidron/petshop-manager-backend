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
            "name": "Tab separated (User example)",
            "content": "nome\tsku\tdescricao\tcategoria\tpreco_venda\tcusto\tquantidade\testoque_minimo\tcodigo_barras\tncm\tcest\tcfop\tcsosn\tcst_pis\tcst_cofins\nProduto csv 1\tSKU-001\tDescrição do produto 1\tcategoria 1\t29.9\t15\t10\t2\t7.89123E+12\t3801.10.00\t01.001.00\t5102\t102\t1\t1"
        },
        {
            "name": "Semicolon separated (Brazilian common)",
            "content": "nome;sku;preco_venda;custo;quantidade\nProduto B;SKU-002;29,90;15,00;10"
        },
        {
            "name": "Comma separated (Standard)",
            "content": "Nome,SKU,Preco_Venda,Custo,Quantidade\nProduto C,SKU-003,29.90,15.00,10"
        },
        {
            "name": "Mixed format numbers",
            "content": "nome;preco_venda;custo\nProduto D;R$ 1.234,56;100.00"
        }
    ]
    
    for case in test_cases:
        print(f"Testing: {case['name']}")
        result = await service.import_products_from_csv(db, tenant_id, case['content'])
        print(f"  Result: {result}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"    Error: {err}")
        
    print("\nVerifying last created product data (Mixed format numbers):")
    # Get args of last call to create
    last_call = service.repository.create.call_args
    if last_call:
        data = last_call[0][2] # db, tenant_id, data
        print(f"  Name: {data.name}")
        print(f"  Price: {data.price}")
        print(f"  Cost: {data.cost}")
    else:
        print("  No calls to repository.create found!")

if __name__ == "__main__":
    asyncio.run(run_test())
