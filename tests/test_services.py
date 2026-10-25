import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.tenant_services.service import ServiceService
from app.modules.tenant_services.repository import ServiceRepository
from app.modules.tenant_services.schemas import ServiceCreate, ServiceUpdate
from app.modules.tenant_services.models import Service


@pytest.fixture
def service_service():
    return ServiceService()


# ==============================================================================
# 1. TESTES DE GESTÃO DO CATÁLOGO DE SERVIÇOS (CRUD)
# ==============================================================================

def test_service_crud(
    db: Session,
    tenant_id: int,
    service_service: ServiceService,
):
    """Testa criação, leitura, atualização e exclusão de serviços."""
    # 1. Create
    data = ServiceCreate(
        name="Hidratação Profunda Ozonizada",
        description="Tratamento capilar intensivo com ozônio",
        species=["Canino"],
        sizes=["P", "M"],
        coat_types=["long", "double"],
        price_cents=8500,
        duration_minutes=40,
        is_active=True,
    )
    service = service_service.create(db, tenant_id, data)
    assert service.id is not None
    assert service.name == "Hidratação Profunda Ozonizada"
    assert service.price_cents == 8500
    assert service.duration_minutes == 40
    assert "Canino" in service.species
    assert service.tenant_id == tenant_id

    # 2. Get by ID
    fetched = service_service.get(db, tenant_id, service.id)
    assert fetched.id == service.id
    assert fetched.name == service.name

    # 3. List
    all_services = service_service.list(db, tenant_id)
    assert any(s.id == service.id for s in all_services)

    # 4. Update
    update_data = ServiceUpdate(
        name="Hidratação Profunda Ozonizada Plus",
        price_cents=9500,
    )
    updated = service_service.update(db, tenant_id, service.id, update_data)
    assert updated.name == "Hidratação Profunda Ozonizada Plus"
    assert updated.price_cents == 9500

    # 5. Delete (Desativação)
    service_service.delete(db, tenant_id, service.id)
    with pytest.raises(HTTPException) as exc_info:
        service_service.get(db, tenant_id, service.id)
    assert exc_info.value.status_code == 404


def test_get_service_not_found_raises_404(
    db: Session,
    tenant_id: int,
    service_service: ServiceService,
):
    """Testa busca de serviço inexistente retornando 404."""
    with pytest.raises(HTTPException) as exc_info:
        service_service.get(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE VALIDAÇÃO DE CONFLITO MULTIDIMENSIONAL (Espécie, Porte, Pelagem)
# ==============================================================================

def test_service_conflict_detection_and_differentiation(
    db: Session,
    tenant_id: int,
    service_service: ServiceService,
):
    """
    Testa a inteligência de validação de duplicidade:
    - Impede cadastrar serviço com o mesmo nome e mesma sobreposição de Espécie + Porte + Pelagem (HTTP 400).
    - Permite cadastrar serviço com mesmo nome se o porte for diferente (ex: Tosa Porte P vs Tosa Porte G).
    - Permite cadastrar serviço com mesmo nome se a espécie for diferente (ex: Canino vs Felino).
    """
    # 1. Cadastra Serviço Base: "Tosa Geral" para Canino, Porte P, Pelagem Longa
    s1 = service_service.create(
        db, tenant_id,
        ServiceCreate(
            name="Tosa Geral Conflito Teste",
            species=["Canino"],
            sizes=["P"],
            coat_types=["long"],
            price_cents=7000,
        ),
    )
    assert s1.id is not None

    # 2. Tentativa de cadastrar serviço idêntico nas 3 dimensões -> deve falhar com 400
    with pytest.raises(HTTPException) as exc_info:
        service_service.create(
            db, tenant_id,
            ServiceCreate(
                name="Tosa Geral Conflito Teste",
                species=["Canino"],
                sizes=["P"],
                coat_types=["long"],
                price_cents=7500,
            ),
        )
    assert exc_info.value.status_code == 400
    assert "Já existe um serviço" in exc_info.value.detail

    # 3. Mesmo nome, mas porte diferente (Porte G) -> DEVE PERMITIR
    s_diff_size = service_service.create(
        db, tenant_id,
        ServiceCreate(
            name="Tosa Geral Conflito Teste",
            species=["Canino"],
            sizes=["G"],
            coat_types=["long"],
            price_cents=11000,
        ),
    )
    assert s_diff_size.id is not None
    assert "G" in s_diff_size.sizes

    # 4. Mesmo nome, mas espécie diferente (Felino) -> DEVE PERMITIR
    s_diff_species = service_service.create(
        db, tenant_id,
        ServiceCreate(
            name="Tosa Geral Conflito Teste",
            species=["Felino"],
            sizes=["P"],
            coat_types=["long"],
            price_cents=8000,
        ),
    )
    assert s_diff_species.id is not None
    assert "Felino" in s_diff_species.species


# ==============================================================================
# 3. TESTES DE NORMALIZAÇÃO AUTOMÁTICA DE ENTRADA
# ==============================================================================

def test_service_normalization_validators():
    """Testa se variações como 'cachorro', 'gato' e 'cão' são normalizadas para os padrões do sistema."""
    # Teste cachorro -> Canino
    s1 = ServiceCreate(
        name="Banho Dog",
        species=["cachorro"],
        sizes=["p"],
        price_cents=5000,
    )
    assert s1.species == ["Canino"]

    # Teste gato -> Felino
    s2 = ServiceCreate(
        name="Banho Cat",
        species=["gato"],
        sizes=["p"],
        price_cents=5000,
    )
    assert s2.species == ["Felino"]


# ==============================================================================
# 4. TESTES DE EXPORTAÇÃO PARA EXCEL
# ==============================================================================

def test_service_export_to_excel(
    db: Session,
    tenant_id: int,
    service_service: ServiceService,
):
    """Testa exportação da tabela de serviços para formato Excel (.xlsx)."""
    excel_bytes = service_service.export_to_excel(db, tenant_id)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0
