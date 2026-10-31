from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy.orm import Session

from app.modules.appointments.models import (
    Appointment,
    AppointmentAction,
    AppointmentStatus,
)
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentItemCreate,
    AppointmentRecurrence,
    AppointmentUpdate,
)
from app.modules.appointments.service import AppointmentService
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.tenant_services.models import Service
from app.utils.timezone import get_brazil_now, to_brazil_datetime


@pytest.fixture
def appt_service() -> AppointmentService:
    return AppointmentService()


@pytest.fixture
def second_pet(db: Session, test_client: Client) -> Pet:
    pet = Pet(
        tenant_id=test_client.tenant_id,
        client_id=test_client.id,
        name="Thor Segundo Pet",
        species="Canino",
        breed="Golden",
        size="G",
        is_active=True,
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet


@pytest.fixture
def second_service(db: Session, tenant_id: int) -> Service:
    service = Service(
        tenant_id=tenant_id,
        name="Tosa Higiênica Teste",
        species=["Canino"],
        sizes=["P", "M", "G"],
        price_cents=4500,
        is_active=True,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


def test_create_weekly_recurring_appointments(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Garante que a criação com recorrência semanal gera N agendamentos espaçados em 7 dias."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    created = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            notes="Série semanal",
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id],
                )
            ],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=4),
        ),
    )

    assert created.recurrence_id is not None
    assert created.recurrence_frequency == "weekly"
    assert created.recurrence is not None
    assert created.recurrence["frequency"] == "weekly"
    assert created.recurrence["occurrences"] == 4

    series = (
        db.query(Appointment)
        .filter(
            Appointment.tenant_id == tenant_id,
            Appointment.recurrence_id == created.recurrence_id,
        )
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series) == 4
    for idx, appt in enumerate(series):
        assert appt.scheduled_at == base_time + timedelta(days=7 * idx)
        assert appt.recurrence_frequency == "weekly"
        assert len(appt.items) == 1
        assert appt.items[0].pet_id == test_pet.id


def test_create_biweekly_and_monthly_recurrence_and_limits(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Garante intervalos de 14 dias (quinzenal) e 28 dias (mensal) e limites máximos por frequência."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)

    biweekly = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="biweekly", occurrences=3),
        ),
    )
    bw_series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == biweekly.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(bw_series) == 3
    assert (bw_series[1].scheduled_at - bw_series[0].scheduled_at).days == 14
    assert (bw_series[2].scheduled_at - bw_series[0].scheduled_at).days == 28

    monthly = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="monthly", occurrences=3),
        ),
    )
    mo_series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == monthly.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(mo_series) == 3
    assert (mo_series[1].scheduled_at - mo_series[0].scheduled_at).days == 28

    with pytest.raises(ValidationError):
        AppointmentRecurrence(frequency="monthly", occurrences=13)

    with pytest.raises(ValidationError):
        AppointmentRecurrence(frequency="biweekly", occurrences=27)


def test_update_single_occurrence_detaches_from_recurrence(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Ao editar apenas um agendamento (update_all_future=False), ele se desvincula da série sem afetar os demais."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    rec_id = first.recurrence_id

    updated = appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            notes="Apenas este alterado",
            update_all_future=False,
        ),
    )
    assert updated.recurrence_id is None
    assert updated.recurrence_frequency is None
    assert updated.notes == "Apenas este alterado"

    remaining = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .all()
    )
    assert len(remaining) == 2


def test_update_all_future_shifts_schedule_and_updates_services(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    second_service: Service,
    appt_service: AppointmentService,
):
    """Ao editar com update_all_future=True, desloca o horário e atualiza os serviços dos agendamentos futuros."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            notes="Nota original",
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    rec_id = first.recurrence_id
    new_base_time = base_time + timedelta(hours=2)

    appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            scheduled_at=new_base_time,
            notes="Nota atualizada na série",
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id, second_service.id],
                )
            ],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
            update_all_future=True,
        ),
    )

    series = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series) == 3
    for idx, appt in enumerate(series):
        assert appt.scheduled_at == new_base_time + timedelta(days=7 * idx)
        assert appt.notes == "Nota atualizada na série"
        svc_ids = {s.id for s in appt.items[0].services}
        assert svc_ids == {test_service.id, second_service.id}


def test_update_all_future_expand_and_shrink_occurrences(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Testa expansão (3 -> 5) e redução (5 -> 2) do número de sessões futuras de uma série."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    rec_id = first.recurrence_id

    # Expande para 5
    appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=5),
            update_all_future=True,
        ),
    )
    series_expanded = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_expanded) == 5
    assert series_expanded[4].scheduled_at == base_time + timedelta(days=28)

    # Reduz para 2
    appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=2),
            update_all_future=True,
        ),
    )
    series_shrunk = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_shrunk) == 2


def test_update_all_future_change_frequency_rebuilds_series(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Ao mudar a frequência (ex: weekly -> biweekly), recria as sessões futuras com o novo intervalo."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    rec_id = first.recurrence_id

    appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            recurrence=AppointmentRecurrence(frequency="biweekly", occurrences=4),
            update_all_future=True,
        ),
    )

    series = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series) == 4
    for idx, appt in enumerate(series):
        assert appt.recurrence_frequency == "biweekly"
        assert appt.scheduled_at == base_time + timedelta(days=14 * idx)


def test_remove_recurrence_deletes_future_pending_appointments(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """Remover a recorrência exclui os agendamentos futuros pendentes e limpa recurrence_id do atual."""
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=4),
        ),
    )
    rec_id = first.recurrence_id

    updated = appt_service.update(
        db,
        tenant_id,
        first.id,
        AppointmentUpdate(
            remove_recurrence=True,
            update_all_future=True,
        ),
    )
    assert updated.recurrence_id is None
    assert updated.recurrence_frequency is None

    leftover = (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant_id, Appointment.recurrence_id == rec_id)
        .all()
    )
    assert len(leftover) == 0


def test_cancel_all_future_only_affects_target_series_not_other_pet_series(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    second_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """
    Se um mesmo cliente possui duas séries de recorrência distintas (Pet 1 Semanal e Pet 2 Quinzenal),
    cancelar toda a série do Pet 1 não deve cancelar nem afetar a série do Pet 2.
    """
    base_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)

    pet1_first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    pet2_first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time + timedelta(days=1),
            items=[AppointmentItemCreate(pet_id=second_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="biweekly", occurrences=3),
        ),
    )

    assert pet1_first.recurrence_id != pet2_first.recurrence_id

    # Cancela apenas a 1ª ocorrência do Pet 1 sem cancel_all_future
    appt_service.apply_action(
        db,
        tenant_id,
        pet1_first.id,
        AppointmentAction.CANCEL,
        cancel_all_future=False,
    )
    pet1_series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == pet1_first.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert pet1_series[0].status == AppointmentStatus.CANCELED
    assert pet1_series[1].status == AppointmentStatus.PENDING
    assert pet1_series[2].status == AppointmentStatus.PENDING

    # Agora cancela o 2º agendamento do Pet 1 com cancel_all_future=True
    appt_service.apply_action(
        db,
        tenant_id,
        pet1_series[1].id,
        AppointmentAction.CANCEL,
        cancel_all_future=True,
    )
    db.expire_all()
    pet1_series_after = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == pet1_first.recurrence_id)
        .all()
    )
    assert all(a.status == AppointmentStatus.CANCELED for a in pet1_series_after)

    # Série do Pet 2 continua 100% ativa (PENDING)
    pet2_series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == pet2_first.recurrence_id)
        .all()
    )
    assert len(pet2_series) == 3
    assert all(a.status == AppointmentStatus.PENDING for a in pet2_series)


def test_list_by_client_auto_renews_completed_series(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """
    Se uma série recorrente já estava com todas as sessões concluídas no banco (COMPLETED),
    ao consultar list_by_client ela é renovada automaticamente com um novo ciclo futuro.
    """
    past_time = get_brazil_now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=14)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=past_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=2),
        ),
    )
    for a in db.query(Appointment).filter(Appointment.recurrence_id == first.recurrence_id).all():
        a.status = AppointmentStatus.COMPLETED
    db.commit()

    client_appts = appt_service.list_by_client(db, tenant_id, test_client.id)
    series_appts = sorted(
        [a for a in client_appts if a.recurrence_id == first.recurrence_id],
        key=lambda a: a.scheduled_at,
    )
    assert len(series_appts) == 4
    assert series_appts[0].status == AppointmentStatus.COMPLETED
    assert series_appts[1].status == AppointmentStatus.COMPLETED
    assert series_appts[2].status == AppointmentStatus.PENDING
    assert series_appts[3].status == AppointmentStatus.PENDING
    assert series_appts[2].scheduled_at == series_appts[1].scheduled_at + timedelta(days=7)
    assert series_appts[3].scheduled_at == series_appts[1].scheduled_at + timedelta(days=14)


def test_renew_recurrence_from_completed_appointment(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
    appt_service: AppointmentService,
):
    """
    Ao atualizar a recorrência a partir de um agendamento COMPLETED,
    deve preservar a data histórica do agendamento finalizado e criar N novas sessões futuras.
    """
    past_time = get_brazil_now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=7)
    first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=past_time,
            items=[AppointmentItemCreate(pet_id=test_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=2),
        ),
    )
    series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == first.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    for a in series:
        a.status = AppointmentStatus.COMPLETED
    db.commit()

    last_completed = series[-1]
    original_completed_date = last_completed.scheduled_at
    next_renewal_date = original_completed_date + timedelta(days=7)

    renewed = appt_service.update(
        db,
        tenant_id,
        last_completed.id,
        AppointmentUpdate(
            scheduled_at=next_renewal_date,
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
            update_all_future=True,
        ),
        user_role="employee",
        is_admin=False,
    )

    assert renewed.scheduled_at == original_completed_date
    assert renewed.status == AppointmentStatus.COMPLETED

    all_in_series = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == first.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(all_in_series) == 5
    future_pending = [a for a in all_in_series if a.status == AppointmentStatus.PENDING]
    assert len(future_pending) == 3
    for idx, fa in enumerate(future_pending):
        assert fa.scheduled_at == next_renewal_date + timedelta(days=7 * idx)


def test_auto_renew_recurrence_when_last_session_completes(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    second_pet: Pet,
    test_service: Service,
    second_service: Service,
    appt_service: AppointmentService,
):
    """
    Garante que ao finalizar (COMPLETE) a última sessão de uma série recorrente:
    1. O sistema renova automaticamente a série criando um novo ciclo igual ao anterior
       (mesma frequência, pets, serviços, notas e horário).
    2. Cada pet tem sua própria série renovada de forma independente (Semanal vs Quinzenal).
    3. Se a recorrência for cancelada, não renova automaticamente.
    """
    base_time = get_brazil_now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # Série do Pet 1: Semanal com 3 sessões
    p1_first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time,
            notes="Banho semanal Pet 1",
            items=[
                AppointmentItemCreate(
                    pet_id=test_pet.id,
                    service_ids=[test_service.id, second_service.id],
                )
            ],
            recurrence=AppointmentRecurrence(frequency="weekly", occurrences=3),
        ),
    )
    rec_id_p1 = p1_first.recurrence_id

    series_p1 = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == rec_id_p1)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_p1) == 3

    # Finaliza a 1ª e a 2ª sessão -> ainda resta a 3ª pendente, portanto NÃO deve renovar ainda
    for appt in series_p1[:2]:
        appt_service.apply_action(db, tenant_id, appt.id, AppointmentAction.CONFIRM)
        appt_service.apply_action(db, tenant_id, appt.id, AppointmentAction.START)
        appt_service.apply_action(db, tenant_id, appt.id, AppointmentAction.COMPLETE)

    count_before_last = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == rec_id_p1)
        .count()
    )
    assert count_before_last == 3

    # Agora finaliza a 3ª (última) sessão -> deve renovar automaticamente criando +3 sessões semanais!
    last_appt_p1 = series_p1[2]
    appt_service.apply_action(db, tenant_id, last_appt_p1.id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, last_appt_p1.id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, last_appt_p1.id, AppointmentAction.COMPLETE)

    series_p1_after = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == rec_id_p1)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    assert len(series_p1_after) == 6
    new_future_appts = series_p1_after[3:]
    assert len(new_future_appts) == 3

    for idx, fa in enumerate(new_future_appts, start=1):
        assert fa.status == AppointmentStatus.PENDING
        assert fa.scheduled_at == last_appt_p1.scheduled_at + timedelta(days=7 * idx)
        assert fa.recurrence_frequency == "weekly"
        assert fa.notes == "Banho semanal Pet 1"
        assert len(fa.items) == 1
        assert fa.items[0].pet_id == test_pet.id
        assert {s.id for s in fa.items[0].services} == {test_service.id, second_service.id}

    # Série do Pet 2: Quinzenal com 2 sessões -> se cancelarmos a última sessão, NÃO deve renovar
    p2_first = appt_service.create(
        db,
        tenant_id,
        AppointmentCreate(
            client_id=test_client.id,
            scheduled_at=base_time + timedelta(days=2),
            items=[AppointmentItemCreate(pet_id=second_pet.id, service_ids=[test_service.id])],
            recurrence=AppointmentRecurrence(frequency="biweekly", occurrences=2),
        ),
    )
    series_p2 = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == p2_first.recurrence_id)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    appt_service.apply_action(db, tenant_id, series_p2[0].id, AppointmentAction.CONFIRM)
    appt_service.apply_action(db, tenant_id, series_p2[0].id, AppointmentAction.START)
    appt_service.apply_action(db, tenant_id, series_p2[0].id, AppointmentAction.COMPLETE)

    # Cancela a última sessão com cancel_all_future=True -> não deve renovar
    appt_service.apply_action(
        db, tenant_id, series_p2[1].id, AppointmentAction.CANCEL, cancel_all_future=True
    )
    series_p2_after = (
        db.query(Appointment)
        .filter(Appointment.recurrence_id == p2_first.recurrence_id)
        .all()
    )
    assert len(series_p2_after) == 2



