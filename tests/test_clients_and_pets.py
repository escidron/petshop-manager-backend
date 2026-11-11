from datetime import date, datetime, timezone, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments.models import (
    Appointment,
    AppointmentAction,
    AppointmentAuditLog,
    AppointmentStatus,
)
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentItemCreate,
    AppointmentRecurrence,
)
from app.modules.appointments.service import AppointmentService
from app.modules.clients.models import Client
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import ClientCreate, ClientUpdate
from app.modules.clients.service import ClientService
from app.modules.daycare.models import DaycareStay, DaycareStayStatus
from app.modules.pets.models import Pet
from app.modules.pets.repository import PetRepository
from app.modules.pets.schemas import PetCreate, PetUpdate
from app.modules.pets.service import PetService
from app.modules.tenant_services.models import Service
from app.modules.waiting_list.models import (
    WaitingListEntry,
    WaitingListItem,
    WaitingListPeriod,
    WaitingListStatus,
)


@pytest.fixture
def client_service():
    return ClientService()


@pytest.fixture
def pet_service():
    return PetService()


# ==============================================================================
# 1. TESTES DE GESTÃO DE CLIENTES (ClientService / ClientRepository)
# ==============================================================================

def test_create_and_get_client(
    db: Session,
    tenant_id: int,
    client_service: ClientService,
):
    """Testa criação completa de um cliente com endereço e busca por ID."""
    client_data = ClientCreate(
        name="Carlos Eduardo Silva",
        email="carlos.silva@example.com",
        phone="(11) 98765-4321",
        document_type="cpf",
        document="123.456.789-00",
        birth_date=date(1988, 5, 12),
        cep="01310-100",
        street="Avenida Paulista",
        number="1578",
        complement="Apto 42",
        neighborhood="Bela Vista",
        city="São Paulo",
        state="SP",
        instagram="@carlosedu",
        is_active=True,
    )

    created = client_service.create_client(db, tenant_id, client_data)
    assert created.id is not None
    assert created.name == "Carlos Eduardo Silva"
    assert created.phone == "(11) 98765-4321"
    assert created.city == "São Paulo"
    assert created.tenant_id == tenant_id

    # Busca por ID
    fetched = client_service.get_client(db, tenant_id, created.id)
    assert fetched.id == created.id
    assert fetched.email == "carlos.silva@example.com"
    assert fetched.document == "123.456.789-00"


def test_get_client_not_found_raises_404(
    db: Session,
    tenant_id: int,
    client_service: ClientService,
):
    """Testa se buscar cliente inexistente ou de outro tenant levanta HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        client_service.get_client(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


def test_list_and_update_client(
    db: Session,
    tenant_id: int,
    client_service: ClientService,
):
    """Testa listagem de clientes e atualização cadastral."""
    created = client_service.create_client(
        db, tenant_id,
        ClientCreate(name="Mariana Santos", phone="(21) 97777-6666", is_active=True),
    )

    # Listagem
    clients = client_service.list_clients(db, tenant_id)
    assert any(c.id == created.id for c in clients)

    # Atualização
    update_data = ClientUpdate(
        name="Mariana Santos Oliveira",
        phone="(21) 98888-5555",
        email="mariana.oliveira@example.com",
    )
    updated = client_service.update_client(db, tenant_id, created.id, update_data)
    assert updated.name == "Mariana Santos Oliveira"
    assert updated.phone == "(21) 98888-5555"
    assert updated.email == "mariana.oliveira@example.com"


def test_delete_client(
    db: Session,
    tenant_id: int,
    client_service: ClientService,
):
    """Testa exclusão de cliente e confirma que não é mais encontrado."""
    created = client_service.create_client(
        db, tenant_id,
        ClientCreate(name="Cliente Para Excluir", phone="(31) 95555-4444"),
    )
    client_id = created.id

    client_service.delete_client(db, tenant_id, client_id)

    with pytest.raises(HTTPException) as exc_info:
        client_service.get_client(db, tenant_id, client_id)
    assert exc_info.value.status_code == 404


def test_count_new_clients_with_date_range(
    db: Session,
    tenant_id: int,
    client_service: ClientService,
):
    """Testa contagem de novos clientes dentro de um intervalo de datas."""
    today = date.today()
    # Cria cliente hoje
    client_service.create_client(
        db, tenant_id,
        ClientCreate(name="Cliente Hoje", phone="(11) 91111-2222"),
    )

    count_today = client_service.count_new_clients(
        db, tenant_id, start_date=today, end_date=today
    )
    assert count_today >= 1


def test_generate_import_template_excel(
    client_service: ClientService,
):
    """Testa se o gerador de template Excel para importação de clientes e pets retorna bytes válidos."""
    excel_bytes = client_service.generate_import_template_excel()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


# ==============================================================================
# 2. TESTES DE GESTÃO DE PETS (PetService / PetRepository)
# ==============================================================================

def test_create_and_get_pet(
    db: Session,
    tenant_id: int,
    test_client: Client,
    pet_service: PetService,
):
    """Testa criação de pet vinculado ao cliente com características físicas e busca por ID."""
    pet_data = PetCreate(
        client_id=test_client.id,
        name="Thor",
        species="Canino",
        breed="Golden Retriever",
        gender="Macho",
        is_neutered=True,
        size="G",
        coat_type="Longa",
        coat_color="Dourado",
        age=3,
        age_unit="years",
        birth_date=date(2023, 2, 10),
        notes="Dócil, medo de secador na velocidade máxima.",
        is_active=True,
    )

    created_pet = pet_service.create_pet(db, tenant_id, pet_data)
    assert created_pet.id is not None
    assert created_pet.name == "Thor"
    assert created_pet.species == "Canino"
    assert created_pet.breed == "Golden Retriever"
    assert created_pet.size == "G"
    assert created_pet.client_id == test_client.id
    assert created_pet.tenant_id == tenant_id

    # Busca por ID
    fetched = pet_service.get_pet(db, tenant_id, created_pet.id)
    assert fetched.id == created_pet.id
    assert fetched.notes == "Dócil, medo de secador na velocidade máxima."


def test_create_pet_non_existent_client_raises_404(
    db: Session,
    tenant_id: int,
    pet_service: PetService,
):
    """Testa que tentar criar pet para um cliente inexistente lança HTTP 404."""
    pet_data = PetCreate(
        client_id=999999,
        name="Pet Sem Tutor",
        species="Canino",
        size="P",
    )
    with pytest.raises(HTTPException) as exc_info:
        pet_service.create_pet(db, tenant_id, pet_data)
    assert exc_info.value.status_code == 404
    assert "Cliente não encontrado" in exc_info.value.detail


def test_get_pet_not_found_raises_404(
    db: Session,
    tenant_id: int,
    pet_service: PetService,
):
    """Testa que buscar pet inexistente lança HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        pet_service.get_pet(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


def test_list_pets_by_client(
    db: Session,
    tenant_id: int,
    test_client: Client,
    pet_service: PetService,
):
    """Testa listagem de todos os pets pertencentes a um cliente específico."""
    p1 = pet_service.create_pet(
        db, tenant_id,
        PetCreate(client_id=test_client.id, name="Alfa", species="Canino", size="M"),
    )
    p2 = pet_service.create_pet(
        db, tenant_id,
        PetCreate(client_id=test_client.id, name="Beta", species="Felino", size="P"),
    )

    pets = pet_service.list_pets_by_client(db, tenant_id, test_client.id, include_photos=False)
    pet_names = [p.name for p in pets]
    assert "Alfa" in pet_names
    assert "Beta" in pet_names


def test_update_and_delete_pet(
    db: Session,
    tenant_id: int,
    test_client: Client,
    pet_service: PetService,
):
    """Testa atualização de dados do pet e deleção."""
    created = pet_service.create_pet(
        db, tenant_id,
        PetCreate(client_id=test_client.id, name="Bob", species="Canino", size="P"),
    )

    # Update
    updated = pet_service.update_pet(
        db, tenant_id, created.id,
        PetUpdate(name="Bob Marley", size="M", notes="Castrado recentemente"),
    )
    assert updated.name == "Bob Marley"
    assert updated.size == "M"
    assert updated.notes == "Castrado recentemente"

    # Delete
    pet_service.delete_pet(db, tenant_id, created.id)

    with pytest.raises(HTTPException) as exc_info:
        pet_service.get_pet(db, tenant_id, created.id)
    assert exc_info.value.status_code == 404


def test_mark_pet_deceased_cancels_single_pet_appointments_and_recurrence(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    pet_service: PetService,
):
    """
    Se um pet tem agendamentos abertos (PENDING / CONFIRMED, inclusive recorrentes)
    apenas para ele e é marcado como óbito (is_deceased=True):
    - Todos os agendamentos abertos são cancelados automaticamente e recebem nota de óbito.
    - Agendamentos já finalizados (COMPLETED) permanecem intactos no histórico.
    """
    appt_service = AppointmentService()
    pet = pet_service.create_pet(
        db,
        tenant_id,
        PetCreate(client_id=test_client.id, name="Rex", species="Canino", size="M"),
    )

    now = datetime.now(timezone.utc)
    first_appt = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now + timedelta(days=1),
            items=[AppointmentItemCreate(pet_id=pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )

    series_appts = (
        db.query(Appointment)
        .filter(
            Appointment.tenant_id == tenant_id,
            Appointment.recurrence_id == first_appt.recurrence_id,
        )
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_appts) == 3

    # Conclui o primeiro agendamento e confirma o segundo
    appt_service.apply_action(db, tenant_id, series_appts[0].id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, series_appts[0].id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, series_appts[0].id, AppointmentAction.COMPLETE)
    appt_service.apply_action(db, tenant_id, series_appts[1].id, AppointmentAction.CONFIRM)

    # Marca o pet como óbito
    updated_pet = pet_service.update_pet(
        db,
        tenant_id,
        pet.id,
        PetUpdate(is_deceased=True),
    )
    assert updated_pet.is_deceased is True

    db.expire_all()
    refreshed = (
        db.query(Appointment)
        .filter(
            Appointment.tenant_id == tenant_id,
            Appointment.recurrence_id == first_appt.recurrence_id,
        )
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )

    # O primeiro (COMPLETED) permanece COMPLETED
    assert refreshed[0].status == AppointmentStatus.COMPLETED
    # Os futuros (CONFIRMED e PENDING) foram cancelados automaticamente e mantêm o item para histórico
    assert refreshed[1].status == AppointmentStatus.CANCELED
    assert "[Cancelado automaticamente: pet Rex foi a óbito]" in (refreshed[1].notes or "")
    assert len(refreshed[1].items) == 1

    assert refreshed[2].status == AppointmentStatus.CANCELED
    assert "[Cancelado automaticamente: pet Rex foi a óbito]" in (refreshed[2].notes or "")

    logs = (
        db.query(AppointmentAuditLog)
        .filter(
            AppointmentAuditLog.tenant_id == tenant_id,
            AppointmentAuditLog.appointment_id == refreshed[1].id,
            AppointmentAuditLog.action == "appointment_canceled_deceased",
        )
        .all()
    )
    assert len(logs) == 1


def test_mark_pet_deceased_removes_only_deceased_pet_from_multi_pet_appointment(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_service: Service,
    pet_service: PetService,
):
    """
    Se um agendamento futuro (avulso ou recorrente) possui 2 pets (Pet 1 e Pet 2)
    e apenas o Pet 1 vai a óbito:
    - O Pet 1 é removido dos agendamentos abertos (PENDING / CONFIRMED).
    - O agendamento NÃO é cancelado e continua ativo apenas com o Pet 2.
    - Uma observação e log de auditoria são registrados no agendamento.
    """
    appt_service = AppointmentService()
    pet1 = pet_service.create_pet(
        db,
        tenant_id,
        PetCreate(client_id=test_client.id, name="Bidu", species="Canino", size="P"),
    )
    pet2 = pet_service.create_pet(
        db,
        tenant_id,
        PetCreate(client_id=test_client.id, name="Luna", species="Canino", size="P"),
    )

    now = datetime.now(timezone.utc)
    first_appt = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now + timedelta(days=2),
            items=[
                AppointmentItemCreate(pet_id=pet1.id, service_ids=[test_service.id]),
                AppointmentItemCreate(pet_id=pet2.id, service_ids=[test_service.id]),
            ],
            recurrence=AppointmentRecurrence(frequency="biweekly", occurrences=2),
        ),
    )

    # Marca apenas pet1 (Bidu) como óbito
    pet_service.update_pet(
        db,
        tenant_id,
        pet1.id,
        PetUpdate(is_deceased=True),
    )

    db.expire_all()
    series_appts = (
        db.query(Appointment)
        .filter(
            Appointment.tenant_id == tenant_id,
            Appointment.recurrence_id == first_appt.recurrence_id,
        )
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_appts) == 2

    for appt in series_appts:
        # Continua PENDING (não foi cancelado)
        assert appt.status == AppointmentStatus.PENDING
        # Resta apenas a Luna (pet2)
        remaining_pet_ids = [it.pet_id for it in appt.items]
        assert remaining_pet_ids == [pet2.id]
        assert "[Pet Bidu removido automaticamente do agendamento (óbito)]" in (appt.notes or "")

    # E também verifica Creche (DaycareStay) e Lista de Espera (WaitingListEntry)
    pet3 = pet_service.create_pet(
        db,
        tenant_id,
        PetCreate(client_id=test_client.id, name="Max", species="Canino", size="G"),
    )
    stay = DaycareStay(
        tenant_id=tenant_id,
        client_id=test_client.id,
        pet_id=pet3.id,
        scheduled_start_at=now + timedelta(days=3),
        scheduled_end_at=now + timedelta(days=3, hours=8),
        status=DaycareStayStatus.PENDING.value,
    )
    db.add(stay)

    wl_entry = WaitingListEntry(
        tenant_id=tenant_id,
        client_id=test_client.id,
        preferred_period=WaitingListPeriod.MORNING,
        status=WaitingListStatus.PENDING,
    )
    db.add(wl_entry)
    db.flush()
    wl_item = WaitingListItem(
        waiting_list_entry_id=wl_entry.id,
        pet_id=pet3.id,
        services=[test_service],
    )
    db.add(wl_item)
    db.commit()

    pet_service.update_pet(db, tenant_id, pet3.id, PetUpdate(is_deceased=True))
    db.expire_all()

    refreshed_stay = db.query(DaycareStay).filter(DaycareStay.id == stay.id).first()
    assert refreshed_stay.status == DaycareStayStatus.CANCELED.value
    assert "[Cancelado automaticamente: pet Max foi a óbito]" in (refreshed_stay.notes or "")

    refreshed_wl = db.query(WaitingListEntry).filter(WaitingListEntry.id == wl_entry.id).first()
    assert refreshed_wl.status == WaitingListStatus.CANCELED
    assert "[Cancelado automaticamente: pet Max foi a óbito]" in (refreshed_wl.notes or "")

