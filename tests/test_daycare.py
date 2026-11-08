from datetime import date, datetime
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.client_packages.models import (
    ClientPackage,
    ClientPackageCredit,
    ClientPackagePet,
)
from app.modules.clients.models import Client
from app.modules.daycare.models import (
    DaycareModality,
    DaycareModalityBillingType,
    DaycarePackage,
    DaycareStay,
    DaycareStayAction,
    DaycareStayStatus,
    DaycareStayType,
    DaycareTask,
    DaycareTaskType,
    PetHealthRecord,
)
from app.modules.daycare.schemas import (
    DaycareModalityCreate,
    DaycareModalityUpdate,
    DaycarePackageCreate,
    DaycarePackageUpdate,
    DaycareRecurrenceInput,
    DaycareStayCreate,
    DaycareStayResponse,
    DaycareTaskCreate,
    DaycareTaskUpdate,
    PetHealthRecordCreate,
)
from app.modules.daycare.service import DaycareService
from app.modules.pets.models import Pet
from app.modules.sales.models import Comanda
from app.modules.tenant_services.models import Service
from app.utils.timezone import BRAZIL_TZ


@pytest.fixture(autouse=True)
def ensure_daycare_tables(db: Session):
    """Cria as tabelas de creche dentro da transação de teste (com rollback automático)."""
    bind = db.get_bind()
    DaycareModality.__table__.create(bind=bind, checkfirst=True)
    DaycarePackage.__table__.create(bind=bind, checkfirst=True)
    db.execute(text("ALTER TABLE daycare_modalities ADD COLUMN IF NOT EXISTS species JSON;"))
    DaycareStay.__table__.create(bind=bind, checkfirst=True)
    DaycareTask.__table__.create(bind=bind, checkfirst=True)
    PetHealthRecord.__table__.create(bind=bind, checkfirst=True)
    db.execute(text("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS modality_id INTEGER REFERENCES daycare_modalities(id) ON DELETE SET NULL;"))
    db.execute(text("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS package_id INTEGER REFERENCES daycare_packages(id) ON DELETE SET NULL;"))
    db.execute(text("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS unit_price_cents INTEGER NOT NULL DEFAULT 0;"))
    db.execute(text("ALTER TABLE daycare_stays ADD COLUMN IF NOT EXISTS total_price_cents INTEGER NOT NULL DEFAULT 0;"))


def test_create_daycare_stay_with_tasks_and_timezone_serialization(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    service = DaycareService()
    start_dt = datetime(2026, 11, 2, 8, 0, tzinfo=BRAZIL_TZ)
    end_dt = datetime(2026, 11, 2, 18, 0, tzinfo=BRAZIL_TZ)

    stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            service_id=test_service.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=start_dt,
            scheduled_end_at=end_dt,
            food_info="Ração Premier 120g",
            belongings="Coleira azul e pote inox",
            notes="Cão dócil",
            tasks=[
                DaycareTaskCreate(
                    task_type=DaycareTaskType.FEEDING,
                    scheduled_time="12:00",
                    title="120g Ração Premier",
                ),
                DaycareTaskCreate(
                    task_type=DaycareTaskType.MEDICATION,
                    scheduled_time="14:30",
                    title="1 comp. Apoquel",
                ),
            ],
        ),
    )

    assert stay.id is not None
    assert stay.status == DaycareStayStatus.PENDING.value
    assert stay.food_info == "Ração Premier 120g"
    assert len(stay.tasks) == 2
    assert stay.tasks[0].scheduled_time == "12:00"
    assert stay.tasks[1].scheduled_time == "14:30"

    # Valida serialização Pydantic para fuso de Brasília (-03:00)
    resp = DaycareStayResponse.model_validate(stay)
    dumped = resp.model_dump(mode="json")
    assert dumped["scheduled_start_at"].endswith("-03:00")
    assert dumped["scheduled_end_at"].endswith("-03:00")


def test_multi_day_stay_appears_on_all_days_and_highlights(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    service = DaycareService()
    start_dt = datetime(2026, 11, 10, 8, 30, tzinfo=BRAZIL_TZ)
    end_dt = datetime(2026, 11, 12, 18, 0, tzinfo=BRAZIL_TZ)

    stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            service_id=test_service.id,
            stay_type=DaycareStayType.MULTI_DAY,
            quantity=3,
            scheduled_start_at=start_dt,
            scheduled_end_at=end_dt,
        ),
    )

    for day in [date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)]:
        day_stays = service.list_by_day(db, tenant_id, day)
        assert any(s.id == stay.id for s in day_stays)

    highlights = service.list_highlighted_days(
        db,
        tenant_id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )
    assert date(2026, 11, 10) in highlights
    assert date(2026, 11, 11) in highlights
    assert date(2026, 11, 12) in highlights


def test_checkin_and_checkout_with_package_credit_and_revert(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    # Cria um pacote ativo com 4 créditos para o serviço de creche
    pkg = ClientPackage(
        tenant_id=tenant_id,
        client_id=test_client.id,
        package_name="Pacote Creche 4 Diárias",
        is_active=True,
        is_paid=True,
    )
    db.add(pkg)
    db.flush()
    db.add(ClientPackagePet(client_package_id=pkg.id, pet_id=test_pet.id))
    credit = ClientPackageCredit(
        client_package_id=pkg.id,
        service_id=test_service.id,
        service_name=test_service.name,
        total_qty=4,
        used_qty=0,
    )
    db.add(credit)
    db.commit()

    service = DaycareService()
    stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            service_id=test_service.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=datetime(2026, 11, 3, 8, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 3, 18, 0, tzinfo=BRAZIL_TZ),
        ),
    )
    assert stay.is_package_covered is True

    # 1. Check-in
    checked_in = service.apply_action(db, tenant_id, stay.id, DaycareStayAction.CHECK_IN)
    assert checked_in.status == DaycareStayStatus.CHECKED_IN.value
    assert checked_in.check_in_at is not None

    # 2. Check-out -> Deve consumir 1 crédito do pacote
    checked_out = service.apply_action(db, tenant_id, stay.id, DaycareStayAction.CHECK_OUT)
    assert checked_out.status == DaycareStayStatus.CHECKED_OUT.value
    assert checked_out.check_out_at is not None
    assert checked_out.covered_quantity == 1

    db.refresh(credit)
    assert credit.used_qty == 1

    # 3. Reabrir ou marcar falta -> Deve estornar o crédito do pacote
    reopened = service.apply_action(db, tenant_id, stay.id, DaycareStayAction.REOPEN)
    assert reopened.status == DaycareStayStatus.CHECKED_IN.value
    db.refresh(credit)
    assert credit.used_qty == 0


def test_checkout_without_package_creates_open_comanda_in_pos(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    service = DaycareService()
    stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            service_id=test_service.id,
            stay_type=DaycareStayType.HOURLY,
            quantity=2,  # 2 horas avulsas
            scheduled_start_at=datetime(2026, 11, 4, 14, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 4, 16, 0, tzinfo=BRAZIL_TZ),
        ),
    )

    checked_out = service.apply_action(db, tenant_id, stay.id, DaycareStayAction.CHECK_OUT)
    assert checked_out.status == DaycareStayStatus.CHECKED_OUT.value
    assert checked_out.comanda_id is not None

    comanda = db.query(Comanda).filter(Comanda.id == checked_out.comanda_id).first()
    assert comanda is not None
    assert comanda.status == "open"
    assert float(comanda.total_amount) == float((test_service.price_cents / 100) * 2)


def test_complete_task_and_health_record(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    service = DaycareService()
    stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=datetime(2026, 11, 5, 8, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 5, 18, 0, tzinfo=BRAZIL_TZ),
            tasks=[
                DaycareTaskCreate(
                    task_type=DaycareTaskType.FEEDING,
                    scheduled_time="12:00",
                    title="100g Ração",
                )
            ],
        ),
    )

    task_id = stay.tasks[0].id
    updated_task = service.update_task(
        db,
        tenant_id,
        task_id,
        DaycareTaskUpdate(is_completed=True),
    )
    assert updated_task.is_completed is True
    assert updated_task.completed_at is not None

    # Carteira de vacinas
    rec = service.create_health_record(
        db,
        tenant_id,
        PetHealthRecordCreate(
            pet_id=test_pet.id,
            category="vaccine",
            name="Vacina V10",
            applied_at=date(2026, 1, 15),
            expires_at=date(2027, 1, 15),
            notes="Dose anual",
        ),
    )
    assert rec.id is not None
    records = service.list_health_records_by_pet(db, tenant_id, test_pet.id)
    assert any(r.id == rec.id for r in records)


def test_daycare_recurrence_weekdays(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
    test_service: Service,
):
    """Criação recorrente 'weekdays' (Seg a Sex) pula final de semana corretamente."""
    service = DaycareService()
    # 2026-11-06 é sexta-feira
    first_stay = service.create(
        db,
        tenant_id,
        DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            service_id=test_service.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=datetime(2026, 11, 6, 8, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 6, 18, 0, tzinfo=BRAZIL_TZ),
            recurrence=DaycareRecurrenceInput(frequency="weekdays", occurrences=3),
        ),
    )
    assert first_stay.id is not None

    # Deve ter criado na sexta (06/11), segunda (09/11) e terça (10/11), pulando sábado (07/11) e domingo (08/11)
    days = service.list_highlighted_days(db, tenant_id, date(2026, 11, 6), date(2026, 11, 12))
    assert date(2026, 11, 6) in days
    assert date(2026, 11, 7) not in days
    assert date(2026, 11, 8) not in days
    assert date(2026, 11, 9) in days
    assert date(2026, 11, 10) in days


def test_daycare_modalities_and_checkout_with_hourly_modality(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    """Cria modalidade por hora, testa cobrança no PDV e remoção sem re-seeding automático."""
    service = DaycareService()
    initial_modalities = service.list_modalities(db, tenant_id)
    assert len(initial_modalities) == 0

    hourly_mod = service.create_modality(
        db,
        tenant_id,
        DaycareModalityCreate(
            name="Por hora",
            billing_type=DaycareModalityBillingType.HOURLY,
            price_cents=1500,
            max_hours=1,
        ),
    )
    assert hourly_mod.id is not None
    assert hourly_mod.price_cents == 1500

    # Atualiza preço para R$ 20,00 / hora
    hourly_mod = service.update_modality(
        db,
        tenant_id,
        hourly_mod.id,
        DaycareModalityUpdate(price_cents=2000),
    )
    assert hourly_mod.price_cents == 2000

    # Cria estadia Por Hora (4 horas = R$ 80,00) sem service_id
    stay = service.create(
        db,
        tenant_id,
        DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            modality_id=hourly_mod.id,
            stay_type=DaycareStayType.HOURLY,
            quantity=4,
            scheduled_start_at=datetime(2026, 11, 11, 8, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 11, 12, 0, tzinfo=BRAZIL_TZ),
        ),
    )
    assert stay.unit_price_cents == 2000
    assert stay.total_price_cents == 8000

    checked_out = service.apply_action(db, tenant_id, stay.id, DaycareStayAction.CHECK_OUT)
    assert checked_out.comanda_id is not None
    comanda = db.query(Comanda).filter(Comanda.id == checked_out.comanda_id).first()
    assert comanda is not None
    assert float(comanda.total_amount) == 80.0

    # Verifica que deletar modalidade funciona e não auto-recria nenhuma modalidade
    service.delete_modality(db, tenant_id, hourly_mod.id)
    remaining = service.list_modalities(db, tenant_id)
    assert len(remaining) == 0


def test_daycare_recurrence_custom_weekdays(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    """Criação recorrente com seleção de dias específicos (ex: Seg, Qua, Sex = 1, 3, 5)."""
    service = DaycareService()
    # 2026-11-02 é segunda-feira
    first_stay = service.create(
        db,
        tenant_id,
        DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=datetime(2026, 11, 2, 8, 0, tzinfo=BRAZIL_TZ),
            scheduled_end_at=datetime(2026, 11, 2, 18, 0, tzinfo=BRAZIL_TZ),
            recurrence=DaycareRecurrenceInput(
                frequency="custom",
                weekdays=[1, 3, 5],  # Seg, Qua, Sex (JS day indices)
                weeks_count=2,       # 2 semanas = 6 estadias
            ),
        ),
    )
    assert first_stay.id is not None

    # Semana 1: 02 (Seg), 04 (Qua), 06 (Sex)
    # Semana 2: 09 (Seg), 11 (Qua), 13 (Sex)
    days = service.list_highlighted_days(db, tenant_id, date(2026, 11, 2), date(2026, 11, 15))
    assert date(2026, 11, 2) in days
    assert date(2026, 11, 3) not in days
    assert date(2026, 11, 4) in days
    assert date(2026, 11, 5) not in days
    assert date(2026, 11, 6) in days
    assert date(2026, 11, 7) not in days
    assert date(2026, 11, 8) not in days
    assert date(2026, 11, 9) in days
    assert date(2026, 11, 11) in days
    assert date(2026, 11, 13) in days
    assert len([d for d in days if date(2026, 11, 2) <= d <= date(2026, 11, 15)]) == 6


def test_daycare_modality_with_sizes(
    db: Session,
    tenant_id: int,
):
    """Cria e atualiza modalidade de creche com portes (ex: G, GG)."""
    service = DaycareService()
    created = service.create_modality(
        db,
        tenant_id,
        DaycareModalityCreate(
            name="Diária Porte GG",
            billing_type=DaycareModalityBillingType.DAILY,
            species=["Canino"],
            sizes=["GG"],
            price_cents=8000,
            max_hours=10,
        ),
    )
    assert created.id is not None
    assert created.species == ["Canino"]
    assert created.sizes == ["GG"]
    assert created.price_cents == 8000

    updated = service.update_modality(
        db,
        tenant_id,
        created.id,
        DaycareModalityUpdate(species=["Canino", "Felino"], sizes=["G", "GG"], price_cents=8500),
    )
    assert updated.species == ["Canino", "Felino"]
    assert updated.sizes == ["G", "GG"]
    assert updated.price_cents == 8500


def test_daycare_continuous_recurrence_and_auto_renewal(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    """Testa recorrência contínua com auto-renovação de estadias ao finalizar ciclo."""
    service = DaycareService()
    start_dt = datetime(2026, 11, 2, 8, 0, tzinfo=BRAZIL_TZ)  # Segunda-feira
    end_dt = datetime(2026, 11, 2, 18, 0, tzinfo=BRAZIL_TZ)

    first_stay = service.create(
        db,
        tenant_id,
        DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            unit_price_cents=6000,
            scheduled_start_at=start_dt,
            scheduled_end_at=end_dt,
            food_info="Ração 100g",
            tasks=[
                DaycareTaskCreate(
                    task_type=DaycareTaskType.FEEDING,
                    scheduled_time="12:00",
                    title="Almoço",
                    notes="Servir 100g",
                )
            ],
            recurrence=DaycareRecurrenceInput(
                frequency="custom",
                weekdays=[1, 3],  # Seg, Qua
                weeks_count=1,
                is_continuous=True,
            ),
        ),
    )

    assert first_stay.recurrence_id is not None
    assert first_stay.recurrence_rule["is_continuous"] is True

    # 1 semana com 2 dias = 2 estadias criadas inicialmente
    all_stays = (
        db.query(DaycareStay)
        .filter(DaycareStay.tenant_id == tenant_id, DaycareStay.recurrence_id == first_stay.recurrence_id)
        .order_by(DaycareStay.scheduled_start_at.asc())
        .all()
    )
    assert len(all_stays) == 2

    # Executa check-in e check-out da primeira estadia
    service.apply_action(db, tenant_id, all_stays[0].id, DaycareStayAction.CHECK_IN)
    service.apply_action(db, tenant_id, all_stays[0].id, DaycareStayAction.CHECK_OUT)

    # Ainda resta 1 estadia pendente, não deve auto-renovar ainda
    mid_stays = (
        db.query(DaycareStay)
        .filter(DaycareStay.tenant_id == tenant_id, DaycareStay.recurrence_id == first_stay.recurrence_id)
        .all()
    )
    assert len(mid_stays) == 2

    # Finaliza a segunda estadia -> não resta nenhuma ativa -> dispara auto-renovação
    service.apply_action(db, tenant_id, all_stays[1].id, DaycareStayAction.CHECK_IN)
    service.apply_action(db, tenant_id, all_stays[1].id, DaycareStayAction.CHECK_OUT)

    # Verifica que novas estadias foram geradas mantendo a mesma série e tarefas
    renewed_stays = (
        db.query(DaycareStay)
        .filter(DaycareStay.tenant_id == tenant_id, DaycareStay.recurrence_id == first_stay.recurrence_id)
        .order_by(DaycareStay.scheduled_start_at.asc())
        .all()
    )
    assert len(renewed_stays) > 2
    last_stay = renewed_stays[-1]
    assert last_stay.food_info == "Ração 100g"
    assert len(last_stay.tasks) == 1
    assert last_stay.tasks[0].title == "Almoço"

def test_daycare_update_report(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    """Testa atualizacao incremental do boletim diario (report_data) da estadia."""
    service = DaycareService()
    start_dt = datetime(2026, 11, 2, 8, 0, tzinfo=BRAZIL_TZ)
    end_dt = datetime(2026, 11, 2, 18, 0, tzinfo=BRAZIL_TZ)

    stay = service.create(
        db,
        tenant_id,
        DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            unit_price_cents=6000,
            scheduled_start_at=start_dt,
            scheduled_end_at=end_dt,
        ),
    )
    assert stay.report_data is None

    # Atualiza primeira parte do boletim: refeicao e necessidades
    partial_report = {
        "feeding_status": "ate_all",
        "feeding_obs": "Comeu toda a racao com apetite",
        "pee_status": "normal",
        "poop_status": "normal",
    }
    updated = service.update_report(db, tenant_id, stay.id, partial_report)
    assert updated.report_data["feeding_status"] == "ate_all"
    assert updated.report_data["poop_status"] == "normal"

    # Atualiza adicionando humor e recadinho dos tios
    full_report = {
        **updated.report_data,
        "mood_tags": ["Brincalhao", "Socivel"],
        "best_friend": "Thor",
        "caretaker_notes": "Brincou muito no patio e foi muito carinhoso!",
    }
    updated_again = service.update_report(db, tenant_id, stay.id, full_report)
    assert updated_again.report_data["best_friend"] == "Thor"
    assert "Socivel" in updated_again.report_data["mood_tags"]
    assert updated_again.report_data["feeding_status"] == "ate_all"


def test_daycare_package_crud(
    db: Session,
    tenant_id: int,
):
    """Testa criação de plano mensal (com frequência) e cartela avulsa (com validade e diárias)."""
    service = DaycareService()

    # 1. Cria plano mensal (ex: 3x na semana)
    monthly_pkg = service.create_package(
        db,
        tenant_id,
        DaycarePackageCreate(
            name="Creche 3x na semana",
            price_cents=65000,
            is_monthly=True,
            frequency=3,
        ),
    )
    assert monthly_pkg.id is not None
    assert monthly_pkg.is_monthly is True
    assert monthly_pkg.frequency == 3
    assert monthly_pkg.days_quantity is None
    assert monthly_pkg.validity_days is None
    assert monthly_pkg.price_cents == 65000

    # 2. Cria cartela avulsa (ex: 10 diárias válidas por 90 dias)
    flex_pkg = service.create_package(
        db,
        tenant_id,
        DaycarePackageCreate(
            name="Cartela 10 Diárias de Creche",
            price_cents=70000,
            is_monthly=False,
            days_quantity=10,
            validity_days=90,
        ),
    )
    assert flex_pkg.id is not None
    assert flex_pkg.is_monthly is False
    assert flex_pkg.days_quantity == 10
    assert flex_pkg.validity_days == 90
    assert flex_pkg.frequency is None

    # 3. Lista pacotes
    packages = service.list_packages(db, tenant_id)
    assert len(packages) >= 2

    # 4. Atualiza pacote
    updated = service.update_package(
        db,
        tenant_id,
        monthly_pkg.id,
        DaycarePackageUpdate(price_cents=68000),
    )
    assert updated.price_cents == 68000

    # 5. Deleta pacote
    service.delete_package(db, tenant_id, flex_pkg.id)
    remaining = service.list_packages(db, tenant_id)
    assert all(p.id != flex_pkg.id for p in remaining)


def test_create_daycare_stay_with_monthly_package_and_checkout(
    db: Session,
    tenant_id: int,
    test_client: Client,
    test_pet: Pet,
):
    """Testa agendamento recorrente vinculado a um Pacote Mensal (package_id), gerando cobrança única na Comanda e isentando os dias no check-out."""
    service = DaycareService()

    monthly_pkg = service.create_package(
        db,
        tenant_id,
        DaycarePackageCreate(
            name="Pacote Mensal 3x na semana",
            price_cents=65000,
            is_monthly=True,
            frequency=3,
        ),
    )

    # Segunda-feira 02/11/2026
    start_dt = datetime(2026, 11, 2, 8, 0, tzinfo=BRAZIL_TZ)
    end_dt = datetime(2026, 11, 2, 18, 0, tzinfo=BRAZIL_TZ)

    first_stay = service.create(
        db=db,
        tenant_id=tenant_id,
        data=DaycareStayCreate(
            client_id=test_client.id,
            pet_id=test_pet.id,
            package_id=monthly_pkg.id,
            stay_type=DaycareStayType.DAILY,
            quantity=1,
            scheduled_start_at=start_dt,
            scheduled_end_at=end_dt,
            recurrence=DaycareRecurrenceInput(
                frequency="custom",
                weekdays=[1, 3, 5],  # Seg, Qua, Sex
                weeks_count=4,
                is_continuous=False,
            ),
        ),
    )

    assert first_stay.package_id == monthly_pkg.id
    assert first_stay.is_package_covered is True
    assert first_stay.covered_quantity == 1

    # Verifica que as 12 estadias (3x por 4 semanas) foram criadas com package_id
    stays = (
        db.query(DaycareStay)
        .filter(
            DaycareStay.tenant_id == tenant_id,
            DaycareStay.recurrence_id == first_stay.recurrence_id,
        )
        .all()
    )
    assert len(stays) == 12
    assert all(s.package_id == monthly_pkg.id and s.covered_quantity == 1 for s in stays)

    # Verifica que apenas 1 item com o valor do pacote mensal foi lançado na Comanda aberta do cliente
    comanda = (
        db.query(Comanda)
        .filter(Comanda.tenant_id == tenant_id, Comanda.client_id == test_client.id)
        .first()
    )
    assert comanda is not None
    assert float(comanda.total_amount) == 650.0
    assert len(comanda.items) == 1
    assert "Pacote Mensal 3x na semana" in comanda.items[0].name

    # Faz check-in e check-out do primeiro dia -> não deve duplicar cobrança na comanda
    service.apply_action(db, tenant_id, first_stay.id, DaycareStayAction.CHECK_IN)
    service.apply_action(db, tenant_id, first_stay.id, DaycareStayAction.CHECK_OUT)

    db.refresh(comanda)
    assert float(comanda.total_amount) == 650.0
    assert len(comanda.items) == 1

