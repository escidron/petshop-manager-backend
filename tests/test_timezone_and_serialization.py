from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.schemas import (
    AppointmentResponse,
    ClientSummaryResponse,
    ServiceInAppointmentResponse,
)
from app.modules.clients.schemas import ClientResponse
from app.modules.employees.schemas import PublicAppointment
from app.modules.sales.schemas import ComandaItemResponse
from app.utils.timezone import BRAZIL_TZ


# ==============================================================================
# 1. TESTES DE SERIALIZAÇÃO DE FUSO HORÁRIO (PYDANTIC SCHEMAS)
# ==============================================================================

def test_appointment_response_serializes_in_brazil_timezone():
    """
    Valida que um agendamento gravado como UTC (ex: 00:30 UTC do dia 30)
    seja serializado no JSON exatamente como o horário local de Brasília (-03:00)
    no dia 29 às 21:30.
    """
    dt_scheduled_utc = datetime(2026, 10, 30, 0, 30, 0, tzinfo=timezone.utc)
    dt_created_utc = datetime(2026, 10, 29, 23, 25, 23, 974577, tzinfo=timezone.utc)

    client_summary = ClientSummaryResponse(
        id=915,
        name="Eduardo Sanchez",
        phone="11948808454",
        is_active=True,
        created_at=dt_created_utc,
        pet_names=[],
    )

    appt = AppointmentResponse(
        id=4426,
        scheduled_at=dt_scheduled_utc,
        status=AppointmentStatus.PENDING,
        client=client_summary,
        items=[],
        created_at=dt_created_utc,
    )

    data = appt.model_dump(mode="json")

    assert data["scheduled_at"] == "2026-10-29T21:30:00-03:00"
    assert data["created_at"] == "2026-10-29T20:25:23.974577-03:00"
    assert data["client"]["created_at"] == "2026-10-29T20:25:23.974577-03:00"


def test_client_response_serializes_in_brazil_timezone():
    """Valida serialização de datas de clientes no fuso de Brasília."""
    dt_created_utc = datetime(2026, 10, 29, 23, 0, 0, tzinfo=timezone.utc)
    dt_updated_utc = datetime(2026, 10, 29, 23, 30, 0, tzinfo=timezone.utc)

    client = ClientResponse(
        id=1,
        name="Cliente Teste",
        phone="11999999999",
        is_active=True,
        created_at=dt_created_utc,
        updated_at=dt_updated_utc,
    )

    data = client.model_dump(mode="json")
    assert data["created_at"] == "2026-10-29T20:00:00-03:00"
    assert data["updated_at"] == "2026-10-29T20:30:00-03:00"


def test_public_appointment_and_comanda_item_timezone():
    """Valida serialização de agendamento público e comanda com fuso do Brasil."""
    dt_utc = datetime(2026, 10, 30, 1, 0, 0, tzinfo=timezone.utc)

    public_appt = PublicAppointment(
        id=1,
        scheduled_at=dt_utc,
        status="pending",
        client_name="Cliente Freelancer",
        items=[],
    )
    assert public_appt.model_dump(mode="json")["scheduled_at"] == "2026-10-29T22:00:00-03:00"

    comanda_item = ComandaItemResponse(
        id=1,
        comanda_id=1,
        item_type="service",
        item_id=10,
        name="Banho",
        unit_price=50.0,
        subtotal=50.0,
        appointment_date=dt_utc,
    )
    assert comanda_item.model_dump(mode="json")["appointment_date"] == "2026-10-29T22:00:00-03:00"


# ==============================================================================
# 2. TESTES DE BANCO DE DADOS (LIST_BY_DAY & LIST_HIGHLIGHTED_DAYS)
# ==============================================================================

def test_late_night_appointment_highlighted_and_listed_on_correct_day(
    db: Session,
    tenant_id: int,
    test_client,
):
    """
    Testa agendamento marcado para 21:30 BRT (00:30 UTC do dia seguinte).
    Garante que:
    1. list_by_day(date(2026, 10, 29)) encontra o agendamento.
    2. list_highlighted_days destaca o dia 29 e NÃO o dia 30.
    """
    repo = AppointmentRepository()

    # 21:30 BRT do dia 2026-10-29 (armazena como timestamptz)
    scheduled_at_brt = datetime(2026, 10, 29, 21, 30, 0, tzinfo=BRAZIL_TZ)

    appointment = Appointment(
        tenant_id=tenant_id,
        client_id=test_client.id,
        scheduled_at=scheduled_at_brt,
        status=AppointmentStatus.PENDING,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    # 1. list_by_day para o dia 29
    appts_29 = repo.list_by_day(db, tenant_id, date(2026, 10, 29))
    appt_ids_29 = [a.id for a in appts_29]
    assert appointment.id in appt_ids_29

    # Para o dia 30, esse agendamento NÃO deve aparecer
    appts_30 = repo.list_by_day(db, tenant_id, date(2026, 10, 30))
    appt_ids_30 = [a.id for a in appts_30]
    assert appointment.id not in appt_ids_30

    # 2. list_highlighted_days deve retornar o dia 29 e NÃO o dia 30 para este agendamento
    highlighted = repo.list_highlighted_days(
        db,
        tenant_id,
        start_date=date(2026, 10, 28),
        end_date=date(2026, 10, 31),
    )
    assert date(2026, 10, 29) in highlighted
    assert date(2026, 10, 30) not in highlighted
