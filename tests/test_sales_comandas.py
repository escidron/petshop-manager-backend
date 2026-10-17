import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.modules.sales.repository import SalesRepository
from app.modules.sales.schemas import (
    ComandaSaveRequest,
    ComandaItemCreate,
    SaleCreate,
    SaleItemCreate,
    SalePaymentCreate,
)
from app.modules.sales.models import Comanda, ComandaItem, Sale
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.modules.employees.models import Employee
from app.modules.cash_register.models import CashSession


@pytest.fixture
def repo():
    return SalesRepository()


def test_save_open_comanda_creation(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    test_employee: Employee,
    repo: SalesRepository,
):
    """Testa a criação de uma comanda aberta com itens e cálculo de total."""
    item1 = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
        employee_id=test_employee.id,
        pet_ids=[test_pet.id],
    )
    payload = ComandaSaveRequest(
        client_id=test_client.id,
        items=[item1],
        discount_amount=10.0,
        notes="Comanda de teste inicial",
    )

    comanda = repo.save_open_comanda(db, tenant_id, payload)
    assert comanda is not None
    assert comanda.id is not None
    assert comanda.status == "open"
    assert float(comanda.total_amount) == 50.0  # 60 - 10
    assert float(comanda.discount_amount) == 10.0
    assert len(comanda.items) == 1
    assert comanda.items[0].status == "active"
    assert comanda.items[0].name == test_service.name


def test_remove_single_item_from_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    repo: SalesRepository,
):
    """Testa a remoção de um item específico da comanda mantendo os outros e recalculando o total."""
    # 1. Cria comanda com dois itens distintos
    item1 = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name="Serviço 1",
        quantity=1.0,
        unit_price=50.0,
        subtotal=50.0,
        pet_ids=[test_pet.id],
    )
    item2 = ComandaItemCreate(
        item_type="product",
        item_id=999,
        name="Shampoo Pet",
        quantity=1.0,
        unit_price=30.0,
        subtotal=30.0,
    )
    payload = ComandaSaveRequest(
        client_id=test_client.id,
        items=[item1, item2],
        discount_amount=0.0,
    )
    comanda = repo.save_open_comanda(db, tenant_id, payload)
    assert len(comanda.items) == 2
    assert float(comanda.total_amount) == 80.0

    # 2. Atualiza salvando apenas o item 1 (removendo item 2)
    update_payload = ComandaSaveRequest(
        comanda_id=comanda.id,
        client_id=test_client.id,
        items=[item1],
        discount_amount=0.0,
    )
    updated_comanda = repo.save_open_comanda(db, tenant_id, update_payload)

    # 3. Verifica no banco se o item 2 foi marcado como 'removed'
    all_items = db.query(ComandaItem).filter(ComandaItem.comanda_id == comanda.id).all()
    active_items = [i for i in all_items if i.status == "active"]
    removed_items = [i for i in all_items if i.status == "removed"]

    assert len(active_items) == 1
    assert active_items[0].name == "Serviço 1"
    assert len(removed_items) == 1
    assert removed_items[0].name == "Shampoo Pet"
    assert removed_items[0].removed_at is not None
    assert float(updated_comanda.total_amount) == 50.0


def test_remove_duplicate_item_preserves_remaining(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    repo: SalesRepository,
):
    """
    Testa a remoção de itens duplicados: quando o cliente tem dois serviços idênticos
    no carrinho e remove um deles, apenas UM deve ir para 'removed', mantendo o outro ativo.
    """
    item1 = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
        pet_ids=[test_pet.id],
    )
    item2 = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
        pet_ids=[test_pet.id],
    )
    payload = ComandaSaveRequest(
        client_id=test_client.id,
        items=[item1, item2],
        discount_amount=0.0,
    )
    comanda = repo.save_open_comanda(db, tenant_id, payload)
    assert len([i for i in comanda.items if i.status == "active"]) == 2

    # Remove uma das duplicatas enviando apenas 1 item
    update_payload = ComandaSaveRequest(
        comanda_id=comanda.id,
        client_id=test_client.id,
        items=[item1],
        discount_amount=0.0,
    )
    updated_comanda = repo.save_open_comanda(db, tenant_id, update_payload)

    all_items = db.query(ComandaItem).filter(ComandaItem.comanda_id == comanda.id).all()
    active_items = [i for i in all_items if i.status == "active"]
    removed_items = [i for i in all_items if i.status == "removed"]

    assert len(active_items) == 1
    assert len(removed_items) == 1
    assert float(updated_comanda.total_amount) == 60.0


def test_empty_comanda_cancels_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    repo: SalesRepository,
):
    """Testa que esvaziar o carrinho cancela a comanda automaticamente."""
    item = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
    )
    comanda = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(client_id=test_client.id, items=[item]),
    )
    assert comanda.status == "open"

    # Esvazia a comanda enviando lista vazia de itens
    empty_payload = ComandaSaveRequest(
        comanda_id=comanda.id,
        client_id=test_client.id,
        items=[],
    )
    canceled_comanda = repo.save_open_comanda(db, tenant_id, empty_payload)

    assert canceled_comanda.status == "canceled"
    assert float(canceled_comanda.total_amount) == 0.0

    # Verifica que todos os itens foram marcados como removed
    items = db.query(ComandaItem).filter(ComandaItem.comanda_id == comanda.id).all()
    assert all(i.status == "removed" for i in items)


def test_sale_checkout_closes_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    active_cash_session: CashSession,
    repo: SalesRepository,
):
    """Testa a finalização de venda no caixa: comanda é concluída e venda é registrada."""
    item = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
    )
    comanda = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(client_id=test_client.id, items=[item]),
    )
    assert comanda.status == "open"

    # Finaliza a venda
    sale_payload = SaleCreate(
        client_id=test_client.id,
        comanda_id=comanda.id,
        total_amount=60.0,
        discount_amount=0.0,
        payment_method="pix",
        cash_register_id=active_cash_session.cash_register_id,
        items=[
            SaleItemCreate(
                item_type="service",
                item_id=test_service.id,
                name=test_service.name,
                quantity=1.0,
                unit_price=60.0,
                subtotal=60.0,
            )
        ],
        payments=[
            SalePaymentCreate(
                payment_method="pix",
                amount=60.0,
            )
        ],
    )
    sale = repo.create(db, tenant_id, sale_payload)

    assert sale.id is not None
    assert sale.status == "completed"
    assert sale.comanda_id == comanda.id

    # Comanda deve estar finalizada
    db.refresh(comanda)
    assert comanda.status == "completed"

    # Consulta de comanda aberta do cliente não deve encontrar mais comanda
    open_comanda = repo.get_client_open_comanda(db, tenant_id, test_client.id)
    assert open_comanda is None


def test_sale_checkout_with_partial_payment(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    active_cash_session: CashSession,
    repo: SalesRepository,
):
    """Testa pagamento parcial com saldo em aberto restante."""
    item = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=100.0,
        subtotal=100.0,
    )
    comanda = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(client_id=test_client.id, items=[item]),
    )

    # Cliente paga 70.0 no PIX e fica devendo 30.0
    sale_payload = SaleCreate(
        client_id=test_client.id,
        comanda_id=comanda.id,
        total_amount=70.0,
        discount_amount=0.0,
        payment_method="pix",
        unpaid_remainder=30.0,
        items=[
            SaleItemCreate(
                item_type="service",
                item_id=test_service.id,
                name=test_service.name,
                quantity=1.0,
                unit_price=100.0,
                subtotal=70.0,
            )
        ],
        payments=[
            SalePaymentCreate(
                payment_method="pix",
                amount=70.0,
            )
        ],
    )
    sale = repo.create(db, tenant_id, sale_payload)
    assert sale.status == "completed"

    # A comanda deve continuar aberta com o item 'Saldo em Aberto (Comanda)' de 30.0
    db.refresh(comanda)
    assert comanda.status == "open"
    assert float(comanda.total_amount) == 30.0
    assert any(
        ci.name == "Saldo em Aberto (Comanda)" and float(ci.subtotal) == 30.0
        for ci in comanda.items
    )


def test_checkout_closes_sibling_open_comandas_without_remainder(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    active_cash_session: CashSession,
    repo: SalesRepository,
):
    """
    Testa que ao finalizar uma comanda, qualquer comanda irmã aberta do mesmo cliente
    é fechada, evitando 'ressuscitações' no PDV.
    """
    # Cria comanda 1
    c1 = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(
            client_id=test_client.id,
            items=[
                ComandaItemCreate(
                    item_type="service",
                    item_id=test_service.id,
                    name="Serviço 1",
                    quantity=1.0,
                    unit_price=50.0,
                    subtotal=50.0,
                )
            ],
        ),
    )

    # Cria comanda 2 diretamente
    c2 = Comanda(
        tenant_id=tenant_id,
        client_id=test_client.id,
        status="open",
        total_amount=50.0,
    )
    db.add(c2)
    db.flush()
    ci2 = ComandaItem(
        comanda_id=c2.id,
        item_type="service",
        item_id=test_service.id,
        name="Serviço 2",
        quantity=1.0,
        unit_price=50.0,
        subtotal=50.0,
        status="active",
    )
    db.add(ci2)
    db.commit()

    assert c1.status == "open"
    assert c2.status == "open"

    # Finaliza a venda passando c1
    sale_payload = SaleCreate(
        client_id=test_client.id,
        comanda_id=c1.id,
        total_amount=50.0,
        payment_method="pix",
        items=[
            SaleItemCreate(
                item_type="service",
                item_id=test_service.id,
                name="Serviço 1",
                quantity=1.0,
                unit_price=50.0,
                subtotal=50.0,
            )
        ],
    )
    repo.create(db, tenant_id, sale_payload)

    db.refresh(c1)
    db.refresh(c2)
    assert c1.status == "completed"
    assert c2.status == "completed"


def test_cannot_reopen_completed_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    repo: SalesRepository,
):
    """Garante que requisições tardias ou concorrentes de save_open_comanda não reabrem comanda já finalizada."""
    comanda = Comanda(
        tenant_id=tenant_id,
        client_id=test_client.id,
        status="completed",
        total_amount=50.0,
    )
    db.add(comanda)
    db.commit()
    db.refresh(comanda)

    # Tenta salvar comanda já finalizada
    res = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(
            comanda_id=comanda.id,
            client_id=test_client.id,
            items=[
                ComandaItemCreate(
                    item_type="service",
                    item_id=test_service.id,
                    name=test_service.name,
                    quantity=1.0,
                    unit_price=50.0,
                    subtotal=50.0,
                )
            ],
        ),
    )

    db.refresh(comanda)
    assert comanda.status == "completed"
    assert res.status == "completed"


def test_delete_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    repo: SalesRepository,
):
    """Testa cancelamento explícito de comanda via delete_comanda."""
    item = ComandaItemCreate(
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=60.0,
        subtotal=60.0,
    )
    comanda = repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(client_id=test_client.id, items=[item]),
    )
    assert comanda.status == "open"

    success = repo.delete_comanda(db, tenant_id, comanda.id)
    assert success is True

    db.refresh(comanda)
    assert comanda.status == "canceled"
    assert float(comanda.total_amount) == 0.0
    for ci in comanda.items:
        assert ci.status == "removed"
