import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments.service import AppointmentService
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentItemCreate,
)
from app.modules.appointments.models import (
    Appointment,
    AppointmentStatus,
    AppointmentAction,
    AppointmentItemService,
    AppointmentAuditLog,
    AppointmentPackageCoverage,
)
from app.modules.client_packages.models import (
    ClientPackage,
    ClientPackageCredit,
    ClientPackagePet,
)
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.modules.employees.models import Employee
from app.modules.sales.repository import SalesRepository
from app.modules.sales.schemas import (
    SaleCreate,
    SaleItemCreate,
    SalePaymentCreate,
    ComandaSaveRequest,
)
from app.modules.sales.models import Comanda, Sale


@pytest.fixture
def appt_service():
    return AppointmentService()


@pytest.fixture
def sales_repo():
    return SalesRepository()


def test_appointment_lifecycle_transitions(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Testa o ciclo de vida completo do agendamento: PENDING -> CONFIRMED -> IN_PROGRESS -> COMPLETED."""
    now = datetime.now(timezone.utc) + timedelta(days=1)
    create_data = AppointmentCreate(
        client_id=test_client.id,
        scheduled_at=now,
        notes="Teste de ciclo de vida",
        items=[
            AppointmentItemCreate(
                pet_id=test_pet.id,
                service_ids=[test_service.id],
            )
        ],
    )

    # 1. Criação
    appointment = appt_service.create(db, tenant_id, create_data)
    assert appointment.id is not None
    assert appointment.status == AppointmentStatus.PENDING

    # 2. Confirmação
    confirmed = appt_service.apply_action(
        db, tenant_id, appointment.id, AppointmentAction.CONFIRM
    )
    assert confirmed.status == AppointmentStatus.CONFIRMED

    # 3. Início do serviço
    started = appt_service.apply_action(
        db, tenant_id, appointment.id, AppointmentAction.START
    )
    assert started.status == AppointmentStatus.IN_PROGRESS

    # 4. Finalização
    completed = appt_service.apply_action(
        db, tenant_id, appointment.id, AppointmentAction.COMPLETE
    )
    assert completed.status == AppointmentStatus.COMPLETED

    # 5. Tentativa de ação inválida em agendamento finalizado deve levantar 400
    with pytest.raises(HTTPException) as exc_info:
        appt_service.apply_action(
            db, tenant_id, appointment.id, AppointmentAction.START
        )
    assert exc_info.value.status_code == 400


def test_appointment_completion_uncovered_creates_open_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """
    Ao finalizar um agendamento com serviço avulso (não coberto por pacote),
    o sistema deve automaticamente gerar uma comanda aberta com o serviço para cobrança no caixa.
    """
    now = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now,
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
        ),
    )

    # Avança para CONFIRMED -> IN_PROGRESS -> COMPLETE
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    completed = appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    assert completed.status == AppointmentStatus.COMPLETED
    assert completed.is_paid is False

    # Verifica se a comanda aberta foi criada no módulo de vendas
    open_comanda = sales_repo.get_client_open_comanda(db, tenant_id, test_client.id)
    assert open_comanda is not None
    assert open_comanda.appointment_id == appointment.id
    assert open_comanda.status == "open"
    assert len(open_comanda.items) == 1
    assert open_comanda.items[0].item_id == test_service.id
    assert open_comanda.items[0].status == "active"
    assert float(open_comanda.total_amount) == float(Decimal(test_service.price_cents) / Decimal("100"))


def test_appointment_completion_with_package_credit(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """
    Quando o cliente possui pacote ativo com crédito para o serviço do pet:
    - O crédito deve ser consumido (used_qty passa de 0 para 1).
    - AppointmentPackageCoverage deve ser registrada.
    - Uma venda 'package' (total 0.0) deve ser gerada.
    - O serviço coberto NÃO deve ser cobrado na comanda aberta.
    """
    # 1. Cria um pacote ativo para o cliente e vincula ao pet
    pkg = ClientPackage(
        tenant_id=tenant_id,
        client_id=test_client.id,
        package_name="Pacote Mensal Teste",
        is_active=True,
        is_paid=True,
    )
    db.add(pkg)
    db.flush()

    pet_link = ClientPackagePet(client_package_id=pkg.id, pet_id=test_pet.id)
    db.add(pet_link)

    credit = ClientPackageCredit(
        client_package_id=pkg.id,
        service_id=test_service.id,
        service_name=test_service.name,
        total_qty=4,
        used_qty=0,
    )
    db.add(credit)
    db.commit()

    # 2. Cria e finaliza o agendamento
    now = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now,
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
        ),
    )
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    # 3. Verifica que o crédito foi consumido
    db.refresh(credit)
    assert credit.used_qty == 1

    # 4. Verifica coverage criada
    coverages = (
        db.query(AppointmentPackageCoverage)
        .filter(AppointmentPackageCoverage.service_id == test_service.id)
        .all()
    )
    assert len(coverages) >= 1
    assert coverages[0].client_package_credit_id == credit.id

    # 5. Verifica venda com método 'package'
    package_sale = (
        db.query(Sale)
        .filter(
            Sale.appointment_id == appointment.id,
            Sale.payment_method == "package",
            Sale.status == "completed",
        )
        .first()
    )
    assert package_sale is not None
    assert float(package_sale.total_amount) == 0.0

    # 6. Não deve existir comanda aberta cobrando esse serviço
    open_comanda = sales_repo.get_client_open_comanda(db, tenant_id, test_client.id)
    if open_comanda:
        # Se houver comanda, não deve conter itens ativos deste serviço
        active_items = [ci for ci in open_comanda.items if ci.status == "active" and ci.item_id == test_service.id]
        assert len(active_items) == 0


def test_remove_appointment_service_from_comanda_syncs_appointment(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    test_user,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """
    Testa a sincronização quando o operador do caixa remove um serviço do agendamento da comanda no PDV:
    - O serviço em appointment_item_services deve ser marcado como 'removed'.
    - Um AppointmentAuditLog deve ser gerado preservando a auditoria.
    - O agendamento não fica pendente de pagamento para este serviço removido.
    """
    now = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now,
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
        ),
    )
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    open_comanda = sales_repo.get_client_open_comanda(db, tenant_id, test_client.id)
    assert open_comanda is not None
    assert len([ci for ci in open_comanda.items if ci.status == "active"]) == 1

    # Operador esvazia a comanda no PDV (remove o serviço)
    sales_repo.save_open_comanda(
        db,
        tenant_id,
        ComandaSaveRequest(
            comanda_id=open_comanda.id,
            client_id=test_client.id,
            appointment_id=appointment.id,
            items=[],
        ),
        user_id=test_user.id,
    )

    # Verifica status em appointment_item_services
    ais = (
        db.query(AppointmentItemService)
        .filter(AppointmentItemService.service_id == test_service.id)
        .first()
    )
    assert ais is not None
    assert ais.status == "removed"
    assert ais.removed_by_user_id == test_user.id

    # Verifica que foi criado log de auditoria
    audit_logs = (
        db.query(AppointmentAuditLog)
        .filter(
            AppointmentAuditLog.appointment_id == appointment.id,
            AppointmentAuditLog.action == "service_removed_from_pos",
        )
        .all()
    )
    assert len(audit_logs) >= 1
    assert audit_logs[0].service_id == test_service.id


def test_pos_sale_checkout_marks_appointment_as_paid(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """Testa que após a finalização da venda no caixa, o agendamento é reconhecido como is_paid == True."""
    now = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now,
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
        ),
    )
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    open_comanda = sales_repo.get_client_open_comanda(db, tenant_id, test_client.id)
    assert appointment.is_paid is False

    # Realiza o checkout da comanda no PDV
    sale_payload = SaleCreate(
        client_id=test_client.id,
        appointment_id=appointment.id,
        comanda_id=open_comanda.id,
        total_amount=float(open_comanda.total_amount),
        payment_method="pix",
        items=[
            SaleItemCreate(
                item_type="service",
                item_id=test_service.id,
                name=test_service.name,
                quantity=1.0,
                unit_price=float(open_comanda.total_amount),
                subtotal=float(open_comanda.total_amount),
                appointment_id=appointment.id,
            )
        ],
        payments=[
            SalePaymentCreate(
                payment_method="pix",
                amount=float(open_comanda.total_amount),
            )
        ],
    )
    sale = sales_repo.create(db, tenant_id, sale_payload)
    assert sale.status == "completed"

    # Expira cache do appointment e verifica propriedade is_paid
    db.expire(appointment)
    assert appointment.is_paid is True


def test_pos_delete_service_multi_pet_exact_single_audit_log(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    test_user,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """
    Testa que ao remover o serviço de um dos pets em um agendamento com múltiplos pets:
    1. Apenas 1 log de auditoria é gerado (sem logs duplicados no mesmo milissegundo).
    2. O serviço do outro pet permanece ativo e intocado na comanda.
    3. A sincronização da comanda (sync_client_open_comanda) não realiza hard-delete nem recria itens indevidamente.
    """
    from app.modules.sales.service import SalesService

    # Cria segundo pet para o mesmo cliente
    pet2 = Pet(tenant_id=tenant_id, client_id=test_client.id, name="Safira Teste", species="dog")
    db.add(pet2)
    db.flush()

    now = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=now,
            items=[
                AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id]),
                AppointmentItemCreate(pet_id=pet2.id, service_ids=[test_service.id]),
            ],
        ),
    )
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    open_comanda = sales_repo.get_client_open_comanda(db, tenant_id, test_client.id)
    assert open_comanda is not None
    active_items = [ci for ci in open_comanda.items if ci.status == "active"]
    assert len(active_items) == 2

    pet1_ci = next(ci for ci in active_items if ci.pet_ids == [test_pet.id])
    pet2_ci = next(ci for ci in active_items if ci.pet_ids == [pet2.id])
    assert pet1_ci is not None
    assert pet2_ci is not None

    # Simula o PDV removendo o serviço do pet2 (enviando apenas o pet1 no payload)
    from app.modules.sales.schemas import ComandaItemCreate
    save_payload = ComandaSaveRequest(
        comanda_id=open_comanda.id,
        client_id=test_client.id,
        appointment_id=appointment.id,
        items=[
            ComandaItemCreate(
                item_id=pet1_ci.item_id,
                item_type="service",
                name=pet1_ci.name,
                quantity=1.0,
                unit_price=float(pet1_ci.unit_price),
                subtotal=float(pet1_ci.subtotal),
                pet_ids=pet1_ci.pet_ids,
                appointment_id=pet1_ci.appointment_id,
            )
        ],
    )

    saved_comanda = sales_repo.save_open_comanda(db, tenant_id, save_payload, user_id=test_user.id)
    saved_active = [ci for ci in saved_comanda.items if ci.status == "active"]
    assert len(saved_active) == 1
    assert saved_active[0].pet_ids == [test_pet.id]

    # Verifica que foi criado EXATAMENTE 1 log de auditoria para o pet2 (sem duplicatas)
    audit_logs = (
        db.query(AppointmentAuditLog)
        .filter(
            AppointmentAuditLog.appointment_id == appointment.id,
            AppointmentAuditLog.action == "service_removed_from_pos",
        )
        .all()
    )
    assert len(audit_logs) == 1
    assert audit_logs[0].pet_id == pet2.id
    assert audit_logs[0].service_id == test_service.id

    # Sincroniza a comanda novamente via SalesService
    sales_service = SalesService()
    synced_comanda = sales_service.sync_client_open_comanda(db, tenant_id, test_client.id)
    synced_active = [ci for ci in synced_comanda.items if ci.status == "active"]
    assert len(synced_active) == 1
    assert synced_active[0].pet_ids == [test_pet.id]
    # O ID do item do pet1 não mudou (sem hard delete e recriação)
    assert synced_active[0].id == pet1_ci.id


def test_unpaid_appointment_older_than_30_days_is_synced_to_comanda(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
    sales_repo: SalesRepository,
):
    """
    Testa que um agendamento finalizado há mais de 30 dias (ex: 45 dias atrás)
    e ainda NÃO pago nunca fica para trás: ele deve ser puxado para a comanda aberta do cliente.
    """
    from app.modules.sales.service import SalesService

    past_date = datetime.now(timezone.utc) - timedelta(days=45)
    appointment = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=past_date,
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
        ),
    )
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, appointment.id, AppointmentAction.COMPLETE)

    assert appointment.is_paid is False

    # Sincroniza a comanda do cliente
    sales_service = SalesService()
    comanda = sales_service.sync_client_open_comanda(db, tenant_id, test_client.id)

    assert comanda is not None
    assert comanda.status == "open"
    active_items = [ci for ci in comanda.items if ci.status == "active"]
    assert len(active_items) >= 1
    assert any(ci.item_id == test_service.id and ci.appointment_id == appointment.id for ci in active_items)


