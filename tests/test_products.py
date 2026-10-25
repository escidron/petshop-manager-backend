import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.products.service import ProductService
from app.modules.products.repository import ProductRepository
from app.modules.products.inventory_repository import InventoryRepository
from app.modules.products.schemas import ProductCreate, ProductUpdate
from app.modules.products.models import Product
from app.modules.products.inventory_models import InventoryLog


@pytest.fixture
def product_service():
    return ProductService()


@pytest.fixture
def inventory_repo():
    return InventoryRepository()


# ==============================================================================
# 1. TESTES DE GESTÃO DO CATÁLOGO DE PRODUTOS (CRUD)
# ==============================================================================

def test_product_crud(
    db: Session,
    tenant_id: int,
    product_service: ProductService,
):
    """Testa criação, leitura, atualização e exclusão de produtos."""
    # 1. Create
    product_in = ProductCreate(
        name="Ração Premium Filhotes 15kg",
        sku="RAC-FILH-15KG",
        barcode="7891234567890",
        category="Alimentos",
        price=189.90,
        cost=120.00,
        quantity=10.0,
        min_stock=2.0,
        unit="SC",
        is_active=True,
    )
    product = product_service.create_product(db, tenant_id, product_in)
    assert product.id is not None
    assert product.name == "Ração Premium Filhotes 15kg"
    assert product.sku == "RAC-FILH-15KG"
    assert float(product.price) == 189.90
    assert float(product.quantity) == 10.0

    # 2. Get by ID
    fetched = product_service.get_product(db, tenant_id, product.id)
    assert fetched.id == product.id
    assert fetched.barcode == "7891234567890"

    # 3. List
    all_products = product_service.list_products(db, tenant_id)
    assert any(p.id == product.id for p in all_products)

    # 4. Update
    updated = product_service.update_product(
        db, tenant_id, product.id,
        ProductUpdate(name="Ração Premium Filhotes 15kg - Nova Fórmula", price=199.90),
    )
    assert updated.name == "Ração Premium Filhotes 15kg - Nova Fórmula"
    assert float(updated.price) == 199.90

    # 5. Delete
    product_service.delete_product(db, tenant_id, product.id)
    with pytest.raises(HTTPException) as exc_info:
        product_service.get_product(db, tenant_id, product.id)
    assert exc_info.value.status_code == 404


def test_get_product_not_found_raises_404(
    db: Session,
    tenant_id: int,
    product_service: ProductService,
):
    """Testa busca de produto inexistente retornando 404."""
    with pytest.raises(HTTPException) as exc_info:
        product_service.get_product(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE FILTRO DE USO INTERNO (exclude_internal)
# ==============================================================================

def test_list_products_exclude_internal(
    db: Session,
    tenant_id: int,
    product_service: ProductService,
):
    """
    Testa separação de produtos de prateleira (venda balcão)
    de insumos de uso interno (ex: shampoo de 5L usado na banheira).
    """
    # 1. Produto de varejo (venda ao cliente)
    retail_p = product_service.create_product(
        db, tenant_id,
        ProductCreate(name="Coleira Antipulgas", price=45.00, is_internal_use=False),
    )

    # 2. Produto de uso interno
    internal_p = product_service.create_product(
        db, tenant_id,
        ProductCreate(name="Galão Shampoo Neutro 5L (Uso Banho)", price=90.00, is_internal_use=True),
    )

    # Com exclude_internal=True -> não deve conter o produto de uso interno
    retail_list = product_service.list_products(db, tenant_id, exclude_internal=True)
    retail_ids = {p.id for p in retail_list}
    assert retail_p.id in retail_ids
    assert internal_p.id not in retail_ids

    # Com exclude_internal=False -> deve conter ambos
    full_list = product_service.list_products(db, tenant_id, exclude_internal=False)
    full_ids = {p.id for p in full_list}
    assert retail_p.id in full_ids
    assert internal_p.id in full_ids


# ==============================================================================
# 3. TESTES DE AJUSTE DE ESTOQUE E HISTÓRICO (InventoryLog)
# ==============================================================================

def test_adjust_stock_and_inventory_audit_log(
    db: Session,
    tenant_id: int,
    product_service: ProductService,
    inventory_repo: InventoryRepository,
):
    """
    Testa movimentação de estoque:
    - Entrada de estoque (+10) atualiza quantidade e cria log de movimentação
    - Saída de estoque (-3) atualiza quantidade e cria log de saída
    """
    product = product_service.create_product(
        db, tenant_id,
        ProductCreate(name="Brinquedo Mordedor", price=25.00, quantity=5.0),
    )

    # 1. Entrada de estoque (+15)
    adjusted_in = product_service.adjust_stock(
        db, tenant_id, product.id,
        quantity_change=15.0,
        change_type="purchase",
        notes="Entrada NF 9876",
    )
    assert float(adjusted_in.quantity) == 20.0  # 5 + 15

    # 2. Saída manual de estoque (-4)
    adjusted_out = product_service.adjust_stock(
        db, tenant_id, product.id,
        quantity_change=-4.0,
        change_type="loss",
        notes="Avaria / danificado",
    )
    assert float(adjusted_out.quantity) == 16.0  # 20 - 4

    # 3. Valida histórico em InventoryLog
    logs = inventory_repo.list_logs(db, tenant_id, product_id=product.id)
    assert len(logs) == 2
    types = [l.change_type for l in logs]
    assert "purchase" in types
    assert "loss" in types


# ==============================================================================
# 4. TESTES DE NORMALIZAÇÃO DE SCHEMAS (Price em Cents)
# ==============================================================================

def test_product_schema_normalization():
    """Testa se o validador do Pydantic converte price_cents para price float automaticamente."""
    payload = {
        "name": "Biscoito Canino",
        "price_cents": 1550,  # 15.50
        "cost_cents": 900,    # 9.00
    }
    p = ProductCreate(**payload)
    assert p.price == 15.50
    assert p.cost == 9.00
