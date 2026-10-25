import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.packages.service import PackageService
from app.modules.packages.repository import PackageRepository
from app.modules.packages.schemas import (
    PackageCreate,
    PackageUpdate,
    PackageItemCreate,
)
from app.modules.packages.models import Package, PackageItem
from app.modules.client_packages.service import ClientPackageService
from app.modules.client_packages.repository import ClientPackageRepository
from app.modules.client_packages.schemas import ClientPackageSellRequest
from app.modules.client_packages.models import (
    ClientPackage,
    ClientPackageCredit,
    ClientPackagePet,
    ClientPackageUsage,
)
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.modules.users.models import User


@pytest.fixture
def package_service():
    return PackageService()


@pytest.fixture
def client_package_service():
    return ClientPackageService()


@pytest.fixture
def client_package_repo():
    return ClientPackageRepository()


# ==============================================================================
# 1. TESTES DO CATÁLOGO DE PACOTES (PackageService / PackageRepository)
# ==============================================================================

def test_package_catalog_crud(
    db: Session,
    tenant_id: int,
    test_service: Service,
    package_service: PackageService,
):
    """Testa criação, leitura, atualização e deleção de pacotes no catálogo."""
    # 1. Create
    pkg_in = PackageCreate(
        name="Pacote Mensal 4 Banhos",
        description="4 banhos para cães pequenos",
        price_cents=20000,
        validity_days=30,
        is_active=True,
        items=[
            PackageItemCreate(service_id=test_service.id, quantity=4)
        ],
    )
    pkg = package_service.create_package(db, tenant_id, pkg_in)
    assert pkg.id is not None
    assert pkg.name == "Pacote Mensal 4 Banhos"
    assert pkg.price_cents == 20000
    assert len(pkg.items) == 1
    assert pkg.items[0].service_id == test_service.id
    assert pkg.items[0].quantity == 4

    # 2. Get by ID
    fetched = package_service.get_package(db, tenant_id, pkg.id)
    assert fetched.id == pkg.id
    assert fetched.name == pkg.name

    # 3. List
    all_pkgs = package_service.list_packages(db, tenant_id)
    assert any(p.id == pkg.id for p in all_pkgs)

    # 4. Update
    update_in = PackageUpdate(
        name="Pacote Mensal 4 Banhos - Atualizado",
        price_cents=22000,
    )
    updated = package_service.update_package(db, tenant_id, pkg.id, update_in)
    assert updated.name == "Pacote Mensal 4 Banhos - Atualizado"
    assert updated.price_cents == 22000

    # 5. Export to Excel
    excel_bytes = package_service.export_to_excel(db, tenant_id)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # 6. Delete
    package_service.delete_package(db, tenant_id, pkg.id)
    with pytest.raises(HTTPException) as exc_info:
        package_service.get_package(db, tenant_id, pkg.id)
    assert exc_info.value.status_code == 404


def test_package_get_not_found_raises_404(
    db: Session,
    tenant_id: int,
    package_service: PackageService,
):
    """Testa se buscar um pacote inexistente levanta 404."""
    with pytest.raises(HTTPException) as exc_info:
        package_service.get_package(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE VENDA DE PACOTES PARA CLIENTES (ClientPackageService.sell)
# ==============================================================================

def test_sell_package_to_client_single_pet(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_service: ClientPackageService,
):
    """Testa a venda de um pacote de serviços para um cliente com 1 pet."""
    pkg = Package(
        tenant_id=tenant_id,
        name="Pacote Banho 4x",
        price_cents=18000,
        validity_days=45,
        is_active=True,
    )
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=4))
    db.commit()

    sell_req = ClientPackageSellRequest(
        package_id=pkg.id,
        pet_ids=[test_pet.id],
    )
    client_pkg_resp = client_package_service.sell(
        db=db,
        tenant_id=tenant_id,
        client_id=test_client.id,
        data=sell_req,
        is_paid=True,
    )

    assert client_pkg_resp.id is not None
    assert client_pkg_resp.package_name == "Pacote Banho 4x"
    assert client_pkg_resp.is_active is True
    assert len(client_pkg_resp.pets) == 1
    assert client_pkg_resp.pets[0].id == test_pet.id
    assert len(client_pkg_resp.credits) == 1
    credit = client_pkg_resp.credits[0]
    assert credit.service_id == test_service.id
    assert credit.total_qty == 4
    assert credit.used_qty == 0
    assert credit.remaining_qty == 4
    assert client_pkg_resp.expires_at is not None


def test_sell_package_shared_multi_pet(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_service: ClientPackageService,
):
    """Testa a venda de um pacote compartilhado entre dois pets do mesmo tutor."""
    # Cria segundo pet para o mesmo cliente
    pet2 = Pet(
        tenant_id=tenant_id,
        client_id=test_client.id,
        name="Segundo Pet",
        species="Canino",
        size="P",
        is_active=True,
    )
    db.add(pet2)
    db.commit()

    pkg = Package(
        tenant_id=tenant_id,
        name="Pacote Banho Multi-Pet 8x",
        price_cents=32000,
        is_active=True,
    )
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=8))
    db.commit()

    sell_req = ClientPackageSellRequest(
        package_id=pkg.id,
        pet_ids=[test_pet.id, pet2.id],
    )
    res = client_package_service.sell(
        db=db,
        tenant_id=tenant_id,
        client_id=test_client.id,
        data=sell_req,
    )

    assert len(res.pets) == 2
    pet_ids = {p.id for p in res.pets}
    assert test_pet.id in pet_ids
    assert pet2.id in pet_ids
    assert res.credits[0].total_qty == 8


def test_sell_package_validations(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_service: ClientPackageService,
):
    """Testa validações de venda: pet de outro cliente, pacote inativo e pacote sem serviços."""
    # 1. Outro cliente e pet
    other_client = Client(
        tenant_id=tenant_id,
        name="Outro Cliente",
        phone="(11) 98888-7777",
        is_active=True,
    )
    db.add(other_client)
    db.commit()
    other_pet = Pet(
        tenant_id=tenant_id,
        client_id=other_client.id,
        name="Pet Alheio",
        species="Canino",
        size="P",
        is_active=True,
    )
    db.add(other_pet)
    db.commit()

    pkg = Package(tenant_id=tenant_id, name="Pacote Teste", price_cents=5000, is_active=True)
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=2))
    db.commit()

    # Tentativa de vender pacote do test_client informando pet do other_client
    with pytest.raises(HTTPException) as exc_info:
        client_package_service.sell(
            db, tenant_id, test_client.id,
            ClientPackageSellRequest(package_id=pkg.id, pet_ids=[other_pet.id]),
        )
    assert exc_info.value.status_code == 404

    # 2. Pacote inativo
    pkg.is_active = False
    db.commit()
    with pytest.raises(HTTPException) as exc_info:
        client_package_service.sell(
            db, tenant_id, test_client.id,
            ClientPackageSellRequest(package_id=pkg.id, pet_ids=[test_pet.id]),
        )
    assert exc_info.value.status_code == 404

    # 3. Pacote sem serviços (ex: apenas produtos ou vazio)
    pkg_empty = Package(tenant_id=tenant_id, name="Pacote Vazio", price_cents=1000, is_active=True)
    db.add(pkg_empty)
    db.commit()
    with pytest.raises(HTTPException) as exc_info:
        client_package_service.sell(
            db, tenant_id, test_client.id,
            ClientPackageSellRequest(package_id=pkg_empty.id, pet_ids=[test_pet.id]),
        )
    assert exc_info.value.status_code == 400


# ==============================================================================
# 3. TESTES DE CONSUMO MANUAL E DEPLEÇÃO DE CRÉDITOS
# ==============================================================================

def test_consume_credit_lifecycle_and_auto_deactivation(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    test_user: User,
    client_package_service: ClientPackageService,
):
    """
    Testa o consumo manual de créditos:
    - Incrementa used_qty
    - Gera histórico em ClientPackageUsage (change_qty=1)
    - Desativa automaticamente o pacote quando atinge total_qty
    - Impede overconsumption lançando 400
    """
    pkg = Package(tenant_id=tenant_id, name="Pacote Mini 2x", price_cents=8000, is_active=True)
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=2))
    db.commit()

    cp = client_package_service.sell(
        db, tenant_id, test_client.id,
        ClientPackageSellRequest(package_id=pkg.id, pet_ids=[test_pet.id]),
    )
    credit_id = cp.credits[0].id

    # Consumo 1
    c1 = client_package_service.consume_credit(
        db, tenant_id, credit_id, user_id=test_user.id, notes="Baixa manual sessão 1"
    )
    assert c1.used_qty == 1
    assert c1.remaining_qty == 1

    # Verifica se pacote continua ativo
    db_cp = db.query(ClientPackage).filter(ClientPackage.id == cp.id).first()
    assert db_cp.is_active is True

    # Consumo 2 (último crédito)
    c2 = client_package_service.consume_credit(
        db, tenant_id, credit_id, user_id=test_user.id, notes="Baixa manual sessão 2"
    )
    assert c2.used_qty == 2
    assert c2.remaining_qty == 0

    # Verifica se pacote foi desativado automaticamente
    db.refresh(db_cp)
    assert db_cp.is_active is False

    # Verifica histórico de usages
    usages = client_package_service.get_usages(db, tenant_id, cp.id)
    assert len(usages) == 2
    assert all(u.change_qty == 1 for u in usages)
    assert usages[0].user_id == test_user.id

    # Tentativa de consumo além do limite -> deve falhar com 400
    with pytest.raises(HTTPException) as exc_info:
        client_package_service.consume_credit(db, tenant_id, credit_id)
    assert exc_info.value.status_code == 400
    assert "já foram consumidos" in exc_info.value.detail


# ==============================================================================
# 4. TESTES DE ESTORNO / REVERSÃO DE CRÉDITO
# ==============================================================================

def test_revert_credit_reactivates_package(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    test_user: User,
    client_package_service: ClientPackageService,
):
    """
    Testa estorno de crédito consumido:
    - Decrementa used_qty
    - Adiciona log negativo em ClientPackageUsage (change_qty=-1)
    - Reativa o pacote (is_active volta para True) se estava esgotado
    - Impede estorno quando used_qty == 0
    """
    pkg = Package(tenant_id=tenant_id, name="Pacote 1x", price_cents=4000, is_active=True)
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=1))
    db.commit()

    cp = client_package_service.sell(
        db, tenant_id, test_client.id,
        ClientPackageSellRequest(package_id=pkg.id, pet_ids=[test_pet.id]),
    )
    credit_id = cp.credits[0].id

    # 1. Consome o único crédito -> pacote fica inativo
    client_package_service.consume_credit(db, tenant_id, credit_id)
    db_cp = db.query(ClientPackage).filter(ClientPackage.id == cp.id).first()
    assert db_cp.is_active is False

    # 2. Reverte o crédito -> pacote deve ser reativado
    rev = client_package_service.revert_credit(
        db, tenant_id, credit_id, user_id=test_user.id, notes="Estorno por cancelamento"
    )
    assert rev.used_qty == 0
    assert rev.remaining_qty == 1

    db.refresh(db_cp)
    assert db_cp.is_active is True

    # Verifica log de estorno no usage
    usages = client_package_service.get_usages(db, tenant_id, cp.id)
    # Deve conter 1 consumo (+1) e 1 estorno (-1)
    assert len(usages) == 2
    change_qtys = [u.change_qty for u in usages]
    assert 1 in change_qtys
    assert -1 in change_qtys

    # 3. Tentar estornar novamente quando used_qty == 0 deve falhar com 400
    with pytest.raises(HTTPException) as exc_info:
        client_package_service.revert_credit(db, tenant_id, credit_id)
    assert exc_info.value.status_code == 400
    assert "Nenhum crédito foi consumido" in exc_info.value.detail


# ==============================================================================
# 5. TESTES DE TRANSFERÊNCIA DE PACOTE ENTRE PETS
# ==============================================================================

def test_transfer_package_between_pets(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_service: ClientPackageService,
):
    """Testa transferência de pacote entre pets do mesmo tutor e bloqueio entre tutores diferentes."""
    pet_dest = Pet(
        tenant_id=tenant_id,
        client_id=test_client.id,
        name="Pet Destino",
        species="Canino",
        size="P",
        is_active=True,
    )
    db.add(pet_dest)
    db.commit()

    pkg = Package(tenant_id=tenant_id, name="Pacote Transferivel", price_cents=5000, is_active=True)
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=3))
    db.commit()

    cp = client_package_service.sell(
        db, tenant_id, test_client.id,
        ClientPackageSellRequest(package_id=pkg.id, pet_ids=[test_pet.id]),
    )

    # Transfere para o pet_dest do mesmo cliente
    transferred = client_package_service.transfer_package(
        db, tenant_id, cp.id, new_pet_id=pet_dest.id
    )
    assert len(transferred.pets) == 1
    assert transferred.pets[0].id == pet_dest.id

    # Tentativa de transferir para pet de outro tutor -> 400
    other_client = Client(
        tenant_id=tenant_id,
        name="Outro Tutor",
        phone="(11) 98888-6666",
        is_active=True,
    )
    db.add(other_client)
    db.commit()
    other_pet = Pet(
        tenant_id=tenant_id,
        client_id=other_client.id,
        name="Pet de Fora",
        species="Canino",
        size="P",
        is_active=True,
    )
    db.add(other_pet)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        client_package_service.transfer_package(db, tenant_id, cp.id, new_pet_id=other_pet.id)
    assert exc_info.value.status_code == 400


# ==============================================================================
# 6. TESTES DE FIFO E CRÉDITO ATIVO NO REPOSITÓRIO
# ==============================================================================

def test_repo_find_active_credit_fifo_order(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_repo: ClientPackageRepository,
):
    """
    Testa a regra FIFO do repository:
    Quando o cliente tem 2 pacotes idênticos para o mesmo pet:
    - O pacote mais antigo é consumido primeiro
    - Quando o mais antigo esgota, o mais novo passa a ser retornado
    """
    now = datetime.now(timezone.utc)

    # Pacote 1 (Mais antigo - criado 2 dias atrás)
    cp1 = ClientPackage(
        tenant_id=tenant_id,
        client_id=test_client.id,
        package_name="Pacote Antigo",
        is_active=True,
        is_paid=True,
        created_at=now - timedelta(days=2),
    )
    db.add(cp1)
    db.flush()
    db.add(ClientPackagePet(client_package_id=cp1.id, pet_id=test_pet.id))
    credit1 = ClientPackageCredit(
        client_package_id=cp1.id,
        service_id=test_service.id,
        service_name=test_service.name,
        total_qty=1,
        used_qty=0,
    )
    db.add(credit1)

    # Pacote 2 (Mais novo - criado 1 dia atrás)
    cp2 = ClientPackage(
        tenant_id=tenant_id,
        client_id=test_client.id,
        package_name="Pacote Novo",
        is_active=True,
        is_paid=True,
        created_at=now - timedelta(days=1),
    )
    db.add(cp2)
    db.flush()
    db.add(ClientPackagePet(client_package_id=cp2.id, pet_id=test_pet.id))
    credit2 = ClientPackageCredit(
        client_package_id=cp2.id,
        service_id=test_service.id,
        service_name=test_service.name,
        total_qty=2,
        used_qty=0,
    )
    db.add(credit2)
    db.commit()

    # 1. Busca ativo -> Deve vir o credit1 (mais antigo)
    active_credit = client_package_repo.find_active_credit(db, tenant_id, test_pet.id, test_service.id)
    assert active_credit is not None
    assert active_credit.id == credit1.id
    assert active_credit.client_package_id == cp1.id

    # 2. Consome o crédito 1 -> esgota cp1
    success = client_package_repo.consume_credit(db, active_credit, notes="Consumo 1")
    assert success is True
    assert active_credit.used_qty == 1

    # cp1 deve estar inativo
    db.refresh(cp1)
    assert cp1.is_active is False

    # 3. Busca ativo novamente -> Agora deve retornar credit2 (FIFO)
    next_credit = client_package_repo.find_active_credit(db, tenant_id, test_pet.id, test_service.id)
    assert next_credit is not None
    assert next_credit.id == credit2.id
    assert next_credit.client_package_id == cp2.id

    # 4. Consumo em crédito já esgotado retorna False e não altera saldo
    overflow = client_package_repo.consume_credit(db, active_credit)
    assert overflow is False
    assert active_credit.used_qty == 1


# ==============================================================================
# 7. TESTES DE FILTROS E LISTAGEM (list_by_client & list_by_pet)
# ==============================================================================

def test_list_client_packages_filters(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    client_package_service: ClientPackageService,
):
    """Testa listagem de pacotes do cliente com active_only=True e list_by_pet."""
    pkg = Package(tenant_id=tenant_id, name="Pacote Teste", price_cents=5000, is_active=True)
    db.add(pkg)
    db.flush()
    db.add(PackageItem(package_id=pkg.id, service_id=test_service.id, quantity=1))
    db.commit()

    cp = client_package_service.sell(
        db, tenant_id, test_client.id,
        ClientPackageSellRequest(package_id=pkg.id, pet_ids=[test_pet.id]),
    )

    # Lista por pet
    pet_pkgs = client_package_service.list_by_pet(db, tenant_id, test_pet.id)
    assert len(pet_pkgs) >= 1
    assert any(p.id == cp.id for p in pet_pkgs)

    # Lista por cliente ativo
    active_pkgs = client_package_service.list_by_client(db, tenant_id, test_client.id, active_only=True)
    assert any(p.id == cp.id for p in active_pkgs)

    # Desativa pacote
    client_package_service.deactivate(db, tenant_id, cp.id)

    # Com active_only=True não deve mais aparecer
    active_pkgs_after = client_package_service.list_by_client(db, tenant_id, test_client.id, active_only=True)
    assert not any(p.id == cp.id for p in active_pkgs_after)

    # Com active_only=False deve aparecer
    all_pkgs = client_package_service.list_by_client(db, tenant_id, test_client.id, active_only=False)
    assert any(p.id == cp.id for p in all_pkgs)
