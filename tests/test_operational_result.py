import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.modules.financial.operational_result_repository import OperationalResultRepository
from app.modules.tenant_services.models import Service
from app.modules.appointments.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemService,
    AppointmentStatus,
)
from app.modules.clients.models import Client
from app.modules.pets.models import Pet


def test_get_monthly_operational_data_executes_cleanly(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    """
    Testa a apuração do Resultado Operacional.
    Garante que a query SQL direta com 's.sizes AS service_sizes' executa sem erro
    de coluna indefinida (UndefinedColumn) e computa a matriz de atendimentos corretamente.
    """
    repo = OperationalResultRepository()
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month

    # 1. Cria um agendamento finalizado no mês atual para o serviço de teste
    appointment = Appointment(
        tenant_id=tenant_id,
        client_id=test_client.id,
        scheduled_at=now,
        status=AppointmentStatus.COMPLETED,
    )
    db.add(appointment)
    db.flush()

    item = AppointmentItem(
        appointment_id=appointment.id,
        pet_id=test_pet.id,
    )
    db.add(item)
    db.flush()

    ais = AppointmentItemService(
        appointment_item_id=item.id,
        service_id=test_service.id,
        status="active",
    )
    db.add(ais)
    db.commit()

    # 2. Chama a consulta do resultado operacional
    result = repo.get_monthly_operational_data(db, tenant_id, year, month)

    assert result is not None
    assert "days_metadata" in result
    assert "rows" in result
    assert "summary" in result

    # 3. Verifica se os metadados dos dias e as linhas de serviços foram computados
    assert len(result["days_metadata"]) >= 28
    rows = result["rows"]
    assert len(rows) >= 1
    assert result["summary"]["total_services"] >= 1
