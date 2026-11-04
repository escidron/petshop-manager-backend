import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.client_packages.models import ClientPackageCredit, ClientPackageUsage
from app.modules.client_packages.repository import ClientPackageRepository
from app.modules.clients.models import Client
from app.modules.daycare.models import (
    DaycareModality,
    DaycareModalityBillingType,
    DaycarePackage,
    DaycareStay,
    DaycareStayAction,
    DaycareStayStatus,
    DaycareTask,
    PetHealthRecord,
)
from app.modules.daycare.repository import DaycareRepository
from app.modules.daycare.schemas import (
    DaycareModalityCreate,
    DaycareModalityUpdate,
    DaycarePackageCreate,
    DaycarePackageUpdate,
    DaycareStayCreate,
    DaycareStayUpdate,
    DaycareTaskCreate,
    DaycareTaskUpdate,
    PetHealthRecordCreate,
)
from app.modules.pets.models import Pet
from app.modules.sales.models import Comanda, ComandaItem, Sale, SaleItem
from app.modules.tenant_services.models import Service
from app.utils.timezone import get_brazil_now, to_brazil_datetime


class DaycareService:
    def __init__(self):
        self.repo = DaycareRepository()
        self.credit_repo = ClientPackageRepository()

    # ---------- MODALIDADES E PREÇOS DA CRECHE ----------
    def list_modalities(
        self,
        db: Session,
        tenant_id: int,
        only_active: bool = False,
    ) -> List[DaycareModality]:
        query = db.query(DaycareModality).filter(DaycareModality.tenant_id == tenant_id)
        if only_active:
            query = query.filter(DaycareModality.is_active == True)
        return query.order_by(DaycareModality.id.asc()).all()

    def create_modality(
        self,
        db: Session,
        tenant_id: int,
        data: DaycareModalityCreate,
    ) -> DaycareModality:
        modality = DaycareModality(
            tenant_id=tenant_id,
            name=data.name.strip(),
            billing_type=data.billing_type.value,
            description=data.description.strip() if data.description else None,
            max_hours=data.max_hours,
            species=data.species,
            sizes=data.sizes,
            price_cents=data.price_cents,
            is_active=data.is_active,
        )
        db.add(modality)
        db.commit()
        db.refresh(modality)
        return modality

    def update_modality(
        self,
        db: Session,
        tenant_id: int,
        modality_id: int,
        data: DaycareModalityUpdate,
    ) -> DaycareModality:
        modality = (
            db.query(DaycareModality)
            .filter(
                DaycareModality.id == modality_id,
                DaycareModality.tenant_id == tenant_id,
            )
            .first()
        )
        if not modality:
            raise HTTPException(status_code=404, detail="Modalidade de creche não encontrada")

        if data.name is not None:
            modality.name = data.name.strip()
        if data.billing_type is not None:
            modality.billing_type = data.billing_type.value
        if data.description is not None:
            modality.description = data.description.strip() if data.description else None
        if data.max_hours is not None:
            modality.max_hours = data.max_hours
        if data.species is not None:
            modality.species = data.species
        if data.sizes is not None:
            modality.sizes = data.sizes
        if data.price_cents is not None:
            modality.price_cents = data.price_cents
        if data.is_active is not None:
            modality.is_active = data.is_active

        db.commit()
        db.refresh(modality)
        return modality

    def delete_modality(
        self,
        db: Session,
        tenant_id: int,
        modality_id: int,
    ) -> None:
        modality = (
            db.query(DaycareModality)
            .filter(
                DaycareModality.id == modality_id,
                DaycareModality.tenant_id == tenant_id,
            )
            .first()
        )
        if not modality:
            raise HTTPException(status_code=404, detail="Modalidade de creche não encontrada")

        db.query(DaycareStay).filter(
            DaycareStay.modality_id == modality_id,
            DaycareStay.tenant_id == tenant_id,
        ).update({DaycareStay.modality_id: None}, synchronize_session=False)

        db.delete(modality)
        db.commit()

    def _validate_modality(
        self,
        db: Session,
        tenant_id: int,
        modality_id: Optional[int],
    ) -> Optional[DaycareModality]:
        if modality_id is None:
            return None
        modality = (
            db.query(DaycareModality)
            .filter(
                DaycareModality.id == modality_id,
                DaycareModality.tenant_id == tenant_id,
            )
            .first()
        )
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidade de creche inválida")
        return modality

    def _validate_client_and_pet(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
    ) -> tuple[Client, Pet]:
        client = (
            db.query(Client)
            .filter(Client.id == client_id, Client.tenant_id == tenant_id)
            .first()
        )
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        pet = (
            db.query(Pet)
            .filter(
                Pet.id == pet_id,
                Pet.client_id == client_id,
                Pet.tenant_id == tenant_id,
            )
            .first()
        )
        if not pet:
            raise HTTPException(status_code=404, detail="Pet não encontrado para este cliente")
        if pet.is_deceased:
            raise HTTPException(
                status_code=400,
                detail=f"Não é possível agendar creche para o pet '{pet.name}', pois consta como óbito.",
            )
        return client, pet

    def _validate_service(
        self,
        db: Session,
        tenant_id: int,
        service_id: Optional[int],
    ) -> Optional[Service]:
        if service_id is None:
            return None
        service = (
            db.query(Service)
            .filter(
                Service.id == service_id,
                Service.tenant_id == tenant_id,
                Service.is_active == True,
            )
            .first()
        )
        if not service:
            raise HTTPException(status_code=400, detail="Serviço inválido ou inativo")
        return service

    def _attach_package_info(self, stay: DaycareStay) -> DaycareStay:
        if stay.covered_quantity and stay.covered_quantity > 0:
            stay.is_package_covered = True
            return stay

        stay.is_package_covered = False
        if not stay.service_id or stay.status in (
            DaycareStayStatus.CHECKED_OUT.value,
            DaycareStayStatus.CANCELED.value,
        ):
            return stay

        pet = getattr(stay, "pet", None)
        if not pet:
            return stay

        now = datetime.now(timezone.utc)
        for pkg in getattr(pet, "client_packages", []) or []:
            if not getattr(pkg, "is_active", False):
                continue
            exp = getattr(pkg, "expires_at", None)
            if exp is not None:
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    continue
            for credit in getattr(pkg, "credits", []) or []:
                if credit.service_id == stay.service_id and (credit.total_qty - credit.used_qty) > 0:
                    stay.is_package_covered = True
                    return stay
        return stay

    def _compute_prices(
        self,
        modality: Optional[DaycareModality],
        service: Optional[Service],
        quantity: int,
        explicit_unit_price_cents: Optional[int],
    ) -> tuple[int, int]:
        qty = max(1, quantity or 1)
        if explicit_unit_price_cents is not None:
            unit_cents = explicit_unit_price_cents
        elif modality is not None:
            unit_cents = modality.price_cents
        elif service is not None:
            unit_cents = service.price_cents
        else:
            unit_cents = 0

        extra_service_cents = (
            service.price_cents if (modality is not None and service is not None) else 0
        )
        total_cents = (unit_cents * qty) + extra_service_cents
        return unit_cents, total_cents

    def create(
        self,
        db: Session,
        tenant_id: int,
        data: DaycareStayCreate,
    ) -> DaycareStay:
        if data.scheduled_end_at < data.scheduled_start_at:
            raise HTTPException(
                status_code=400,
                detail="A data/hora de saída não pode ser anterior à data/hora de entrada.",
            )

        self._validate_client_and_pet(db, tenant_id, data.client_id, data.pet_id)
        modality = self._validate_modality(db, tenant_id, data.modality_id)
        service = self._validate_service(db, tenant_id, data.service_id)

        unit_cents, total_cents = self._compute_prices(
            modality, service, data.quantity, data.unit_price_cents
        )

        base_start = to_brazil_datetime(data.scheduled_start_at)
        base_end = to_brazil_datetime(data.scheduled_end_at)
        duration = base_end - base_start

        offsets_days: list[int] = [0]
        recurrence_id: Optional[str] = None
        recurrence_rule: Optional[dict] = None

        if data.recurrence:
            rec = data.recurrence
            recurrence_id = str(uuid.uuid4())
            recurrence_rule = {
                "weekdays": rec.weekdays,
                "weeks_count": rec.weeks_count,
                "is_continuous": bool(rec.is_continuous),
                "entry_time": base_start.strftime("%H:%M"),
                "exit_time": base_end.strftime("%H:%M"),
            }
            if rec.weekdays and len(rec.weekdays) > 0:
                selected_weekdays = set(rec.weekdays)
                weeks = min(max(rec.weeks_count or 4, 1), 52)
                max_total = min(max(rec.occurrences or (weeks * len(selected_weekdays)), 1), 365)
                offsets_days = []
                d_offset = 0
                while len(offsets_days) < max_total and d_offset < (weeks * 7):
                    candidate = base_start + timedelta(days=d_offset)
                    js_day = (candidate.weekday() + 1) % 7
                    if js_day in selected_weekdays:
                        offsets_days.append(d_offset)
                    d_offset += 1
                if not offsets_days:
                    offsets_days = [0]
            elif rec.occurrences and rec.occurrences > 1:
                freq = rec.frequency or "weekdays"
                count = min(max(rec.occurrences, 2), 60)
                if freq == "daily":
                    offsets_days = [i for i in range(count)]
                elif freq == "weekdays":
                    offsets_days = []
                    d_offset = 0
                    while len(offsets_days) < count:
                        candidate = base_start + timedelta(days=d_offset)
                        if candidate.weekday() < 5:
                            offsets_days.append(d_offset)
                        d_offset += 1
                elif freq == "biweekly":
                    offsets_days = [i * 14 for i in range(count)]
                elif freq == "monthly":
                    offsets_days = [i * 28 for i in range(count)]
                else:
                    offsets_days = [i * 7 for i in range(count)]

        first_stay: Optional[DaycareStay] = None
        for day_offset in offsets_days:
            cur_start = base_start + timedelta(days=day_offset)
            cur_end = cur_start + duration
            stay = DaycareStay(
                tenant_id=tenant_id,
                client_id=data.client_id,
                pet_id=data.pet_id,
                modality_id=data.modality_id,
                service_id=data.service_id,
                stay_type=data.stay_type.value,
                quantity=data.quantity,
                unit_price_cents=unit_cents,
                total_price_cents=total_cents,
                scheduled_start_at=cur_start,
                scheduled_end_at=cur_end,
                status=DaycareStayStatus.PENDING.value,
                food_info=data.food_info,
                belongings=data.belongings,
                notes=data.notes,
                recurrence_id=recurrence_id,
                recurrence_rule=recurrence_rule,
            )
            self.repo.create_stay(db, stay)
            if first_stay is None:
                first_stay = stay

            for t in data.tasks:
                task = DaycareTask(
                    tenant_id=tenant_id,
                    stay_id=stay.id,
                    task_type=t.task_type.value,
                    scheduled_time=t.scheduled_time.strip(),
                    title=t.title.strip(),
                    notes=t.notes,
                    is_completed=False,
                )
                db.add(task)

        db.commit()
        loaded = self.repo.get_by_id(db, tenant_id, first_stay.id)
        return self._attach_package_info(loaded)

    def get(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
    ) -> DaycareStay:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche não encontrado")
        return self._attach_package_info(stay)

    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ) -> List[DaycareStay]:
        stays = self.repo.list_by_day(db, tenant_id, day)
        return [self._attach_package_info(s) for s in stays]

    def list_by_range(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[DaycareStay]:
        stays = self.repo.list_by_range(db, tenant_id, start_date, end_date)
        return [self._attach_package_info(s) for s in stays]

    def list_highlighted_days(
        self,
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[date]:
        return self.repo.list_highlighted_days(db, tenant_id, start_date, end_date)

    def update(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
        data: DaycareStayUpdate,
    ) -> DaycareStay:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche não encontrado")

        if data.modality_id is not None:
            modality = self._validate_modality(db, tenant_id, data.modality_id)
            stay.modality_id = data.modality_id
            stay.modality = modality

        if data.service_id is not None:
            service = self._validate_service(db, tenant_id, data.service_id)
            stay.service_id = data.service_id
            stay.service = service

        if data.stay_type is not None:
            stay.stay_type = data.stay_type.value

        if data.quantity is not None:
            stay.quantity = data.quantity

        if data.scheduled_start_at is not None:
            stay.scheduled_start_at = to_brazil_datetime(data.scheduled_start_at)

        if data.scheduled_end_at is not None:
            stay.scheduled_end_at = to_brazil_datetime(data.scheduled_end_at)

        if stay.scheduled_end_at < stay.scheduled_start_at:
            raise HTTPException(
                status_code=400,
                detail="A data/hora de saída não pode ser anterior à data/hora de entrada.",
            )

        unit_cents, total_cents = self._compute_prices(
            stay.modality,
            stay.service,
            stay.quantity,
            data.unit_price_cents if data.unit_price_cents is not None else stay.unit_price_cents,
        )
        stay.unit_price_cents = unit_cents
        stay.total_price_cents = total_cents

        if data.food_info is not None:
            stay.food_info = data.food_info

        if data.belongings is not None:
            stay.belongings = data.belongings

        if data.notes is not None:
            stay.notes = data.notes

        if data.report_data is not None:
            stay.report_data = data.report_data

        if data.tasks is not None:
            db.query(DaycareTask).filter(
                DaycareTask.stay_id == stay.id,
                DaycareTask.tenant_id == tenant_id,
            ).delete(synchronize_session=False)
            for t in data.tasks:
                db.add(
                    DaycareTask(
                        tenant_id=tenant_id,
                        stay_id=stay.id,
                        task_type=t.task_type.value,
                        scheduled_time=t.scheduled_time.strip(),
                        title=t.title.strip(),
                        notes=t.notes,
                        is_completed=False,
                    )
                )

        db.commit()
        loaded = self.repo.get_by_id(db, tenant_id, stay.id)
        return self._attach_package_info(loaded)

    def update_report(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
        report_data: dict,
    ) -> DaycareStay:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche nao encontrado")
        stay.report_data = report_data
        db.commit()
        loaded = self.repo.get_by_id(db, tenant_id, stay.id)
        return self._attach_package_info(loaded)

    def delete(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
    ) -> None:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche não encontrado")
        db.delete(stay)
        db.commit()

    def apply_action(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
        action: DaycareStayAction,
        notes: Optional[str] = None,
    ) -> DaycareStay:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche não encontrado")

        now_br = get_brazil_now()

        if action == DaycareStayAction.CHECK_IN:
            if stay.status == DaycareStayStatus.CHECKED_IN.value:
                return self._attach_package_info(stay)
            if stay.status not in (
                DaycareStayStatus.PENDING.value,
                DaycareStayStatus.ABSENT.value,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Não é possível realizar check-in no status atual.",
                )
            stay.status = DaycareStayStatus.CHECKED_IN.value
            stay.check_in_at = now_br
            if notes:
                stay.notes = f"{stay.notes}\n{notes}".strip() if stay.notes else notes

        elif action == DaycareStayAction.CHECK_OUT:
            if stay.status == DaycareStayStatus.CHECKED_OUT.value:
                return self._attach_package_info(stay)
            if stay.status not in (
                DaycareStayStatus.CHECKED_IN.value,
                DaycareStayStatus.PENDING.value,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Não é possível realizar check-out no status atual.",
                )
            if not stay.check_in_at:
                stay.check_in_at = stay.scheduled_start_at
            stay.status = DaycareStayStatus.CHECKED_OUT.value
            stay.check_out_at = now_br
            if notes:
                stay.notes = f"{stay.notes}\n{notes}".strip() if stay.notes else notes

            self._process_checkout_billing(db, tenant_id, stay)
            if stay.recurrence_id:
                self._auto_renew_series_if_needed(db, tenant_id, stay.recurrence_id)

        elif action == DaycareStayAction.MARK_ABSENT:
            if stay.status == DaycareStayStatus.CHECKED_OUT.value:
                self._revert_checkout_billing(db, tenant_id, stay)
            stay.status = DaycareStayStatus.ABSENT.value
            stay.check_in_at = None
            stay.check_out_at = None
            if notes:
                stay.notes = f"{stay.notes}\n{notes}".strip() if stay.notes else notes
            if stay.recurrence_id:
                self._auto_renew_series_if_needed(db, tenant_id, stay.recurrence_id)

        elif action == DaycareStayAction.CANCEL:
            if stay.status == DaycareStayStatus.CHECKED_OUT.value:
                self._revert_checkout_billing(db, tenant_id, stay)
            stay.status = DaycareStayStatus.CANCELED.value
            if notes:
                stay.notes = f"{stay.notes}\n{notes}".strip() if stay.notes else notes

        elif action == DaycareStayAction.REOPEN:
            if stay.status == DaycareStayStatus.CHECKED_OUT.value:
                self._revert_checkout_billing(db, tenant_id, stay)
            stay.status = DaycareStayStatus.CHECKED_IN.value
            stay.check_out_at = None

        db.commit()
        loaded = self.repo.get_by_id(db, tenant_id, stay.id)
        return self._attach_package_info(loaded)

    def _auto_renew_series_if_needed(
        self,
        db: Session,
        tenant_id: int,
        recurrence_id: str | None,
    ) -> list[DaycareStay]:
        """
        Auto-renovação de estadias de creche contínuas (quando configurado 'never').
        Quando não há mais estadias pendentes/ativas na série, gera o próximo ciclo de semanas
        mantendo os mesmos dias da semana, horários, pet e tarefas (alimentação/medicação).
        """
        if not recurrence_id:
            return []

        all_in_series = (
            db.query(DaycareStay)
            .filter(
                DaycareStay.tenant_id == tenant_id,
                DaycareStay.recurrence_id == recurrence_id,
            )
            .order_by(DaycareStay.scheduled_start_at.asc(), DaycareStay.id.asc())
            .all()
        )
        if not all_in_series:
            return []

        # Se o último agendamento da série foi cancelado, a recorrência foi encerrada
        if all_in_series[-1].status == DaycareStayStatus.CANCELED.value:
            return []

        rule = all_in_series[-1].recurrence_rule or {}
        if not rule.get("is_continuous"):
            return []

        active_remaining = [
            s
            for s in all_in_series
            if s.status in (DaycareStayStatus.PENDING.value, DaycareStayStatus.CHECKED_IN.value)
        ]
        if len(active_remaining) > 0:
            return []

        last_stay = all_in_series[-1]
        weekdays = rule.get("weekdays")
        if not weekdays or len(weekdays) == 0:
            return []

        selected_weekdays = set(weekdays)
        cycle_weeks = min(max(rule.get("weeks_count") or 52, 1), 52)
        duration = last_stay.scheduled_end_at - last_stay.scheduled_start_at

        # Começar no dia seguinte à última estadia
        base_next = last_stay.scheduled_start_at + timedelta(days=1)
        offsets_days: list[int] = []
        d_offset = 0
        max_total = cycle_weeks * len(selected_weekdays)
        while len(offsets_days) < max_total and d_offset < (cycle_weeks * 7 + 14):
            candidate = base_next + timedelta(days=d_offset)
            js_day = (candidate.weekday() + 1) % 7
            if js_day in selected_weekdays:
                offsets_days.append(d_offset)
            d_offset += 1

        if not offsets_days:
            return []

        # Clonar as tarefas da última estadia como padrão do novo ciclo
        template_tasks = (
            db.query(DaycareTask)
            .filter(
                DaycareTask.stay_id == last_stay.id,
                DaycareTask.tenant_id == tenant_id,
            )
            .all()
        )

        created_stays: list[DaycareStay] = []
        for day_off in offsets_days:
            cur_start = base_next + timedelta(days=day_off)
            cur_end = cur_start + duration

            new_stay = DaycareStay(
                tenant_id=tenant_id,
                client_id=last_stay.client_id,
                pet_id=last_stay.pet_id,
                modality_id=last_stay.modality_id,
                service_id=last_stay.service_id,
                stay_type=last_stay.stay_type,
                quantity=last_stay.quantity,
                unit_price_cents=last_stay.unit_price_cents,
                total_price_cents=last_stay.total_price_cents,
                scheduled_start_at=cur_start,
                scheduled_end_at=cur_end,
                status=DaycareStayStatus.PENDING.value,
                food_info=last_stay.food_info,
                belongings=last_stay.belongings,
                notes=last_stay.notes,
                recurrence_id=recurrence_id,
                recurrence_rule=rule,
            )
            self.repo.create_stay(db, new_stay)
            created_stays.append(new_stay)

            for t in template_tasks:
                db.add(
                    DaycareTask(
                        tenant_id=tenant_id,
                        stay_id=new_stay.id,
                        task_type=t.task_type,
                        scheduled_time=t.scheduled_time,
                        title=t.title,
                        notes=t.notes,
                        is_completed=False,
                    )
                )

        db.commit()
        return created_stays

    def _get_or_create_open_comanda(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        added_subtotal: float,
    ) -> Comanda:
        comanda = (
            db.query(Comanda)
            .filter(
                Comanda.client_id == client_id,
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
            )
            .first()
        )
        if not comanda:
            comanda = Comanda(
                tenant_id=tenant_id,
                client_id=client_id,
                status="open",
                total_amount=added_subtotal,
                discount_amount=0.0,
            )
            db.add(comanda)
            db.flush()
        else:
            comanda.total_amount = float(comanda.total_amount or 0.0) + added_subtotal
        return comanda

    def _process_checkout_billing(
        self,
        db: Session,
        tenant_id: int,
        stay: DaycareStay,
    ) -> None:
        pet_name = stay.pet.name if stay.pet else "Pet"
        qty_needed = max(1, stay.quantity or 1)

        # Caso 1: Estadia com Modalidade própria da Creche (ou unit_price_cents definido sem depender do serviço de banho)
        if stay.modality_id and stay.modality:
            modality_unit_price = Decimal(stay.unit_price_cents or stay.modality.price_cents) / Decimal("100")
            modality_subtotal = float(modality_unit_price * Decimal(str(qty_needed)))
            if modality_subtotal > 0:
                comanda = self._get_or_create_open_comanda(
                    db, tenant_id, stay.client_id, modality_subtotal
                )
                c_item = ComandaItem(
                    comanda_id=comanda.id,
                    item_type="service",
                    item_id=stay.modality.id,
                    name=f"Creche ({stay.modality.name}) - {pet_name}",
                    quantity=qty_needed,
                    unit_price=float(modality_unit_price),
                    subtotal=modality_subtotal,
                    pet_ids=[stay.pet_id],
                    unit="UN",
                )
                db.add(c_item)
                stay.comanda_id = comanda.id

            # Se também houver um serviço extra de Banho e Tosa selecionado (stay.service_id)
            if stay.service_id and stay.service:
                service = stay.service
                credit = self.credit_repo.find_active_credit(
                    db, tenant_id, stay.pet_id, service.id
                )
                real_price = Decimal(service.price_cents) / Decimal("100")
                if credit and self.credit_repo.consume_credit(
                    db, credit, notes=f"Serviço adicional na Creche - Pet: {pet_name}"
                ):
                    stay.covered_quantity = 1
                    stay.client_package_credit_id = credit.id
                    pkg_sale = Sale(
                        tenant_id=tenant_id,
                        client_id=stay.client_id,
                        pet_id=stay.pet_id,
                        total_amount=Decimal("0"),
                        payment_method="package",
                        status="completed",
                    )
                    db.add(pkg_sale)
                    db.flush()
                    db.add(
                        SaleItem(
                            sale_id=pkg_sale.id,
                            item_type="service",
                            item_id=service.id,
                            name=f"{service.name} (Adicional Creche - {pet_name})",
                            quantity=1,
                            unit_price=real_price,
                            subtotal=Decimal("0"),
                        )
                    )
                    stay.sale_id = pkg_sale.id
                else:
                    extra_subtotal = float(real_price)
                    comanda = self._get_or_create_open_comanda(
                        db, tenant_id, stay.client_id, extra_subtotal
                    )
                    db.add(
                        ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=service.id,
                            name=f"{service.name} (Adicional Creche - {pet_name})",
                            quantity=1,
                            unit_price=float(real_price),
                            subtotal=extra_subtotal,
                            pet_ids=[stay.pet_id],
                            unit="UN",
                        )
                    )
                    stay.comanda_id = comanda.id
            return

        # Caso 2: Fluxo legado / pacote direto vinculado a service_id (sem modality_id)
        if not stay.service_id or not stay.service:
            return

        service = stay.service
        covered_qty = 0
        last_credit_id: Optional[int] = None

        for _ in range(qty_needed):
            credit = self.credit_repo.find_active_credit(
                db, tenant_id, stay.pet_id, service.id
            )
            if credit:
                usage_note = f"Consumido via Creche - Pet: {pet_name}"
                if self.credit_repo.consume_credit(db, credit, notes=usage_note):
                    covered_qty += 1
                    last_credit_id = credit.id
                else:
                    break
            else:
                break

        stay.covered_quantity = covered_qty
        stay.client_package_credit_id = last_credit_id

        real_price = Decimal(service.price_cents) / Decimal("100")

        if covered_qty > 0:
            pkg_sale = Sale(
                tenant_id=tenant_id,
                client_id=stay.client_id,
                pet_id=stay.pet_id,
                total_amount=Decimal("0"),
                payment_method="package",
                status="completed",
            )
            db.add(pkg_sale)
            db.flush()

            sale_item = SaleItem(
                sale_id=pkg_sale.id,
                item_type="service",
                item_id=service.id,
                name=f"{service.name} (Creche - {pet_name})",
                quantity=covered_qty,
                unit_price=real_price,
                subtotal=Decimal("0"),
            )
            db.add(sale_item)
            stay.sale_id = pkg_sale.id

        uncovered_qty = qty_needed - covered_qty
        if uncovered_qty > 0:
            extra_subtotal = float(real_price * Decimal(str(uncovered_qty)))
            comanda = self._get_or_create_open_comanda(
                db, tenant_id, stay.client_id, extra_subtotal
            )
            c_item = ComandaItem(
                comanda_id=comanda.id,
                item_type="service",
                item_id=service.id,
                name=f"{service.name} (Creche - {pet_name})",
                quantity=uncovered_qty,
                unit_price=float(real_price),
                subtotal=extra_subtotal,
                pet_ids=[stay.pet_id],
                unit="UN",
            )
            db.add(c_item)
            stay.comanda_id = comanda.id

    def _revert_checkout_billing(
        self,
        db: Session,
        tenant_id: int,
        stay: DaycareStay,
    ) -> None:
        if stay.covered_quantity > 0 and stay.client_package_credit_id:
            credit = (
                db.query(ClientPackageCredit)
                .filter(ClientPackageCredit.id == stay.client_package_credit_id)
                .first()
            )
            if credit:
                refund_qty = min(credit.used_qty, stay.covered_quantity)
                credit.used_qty = max(0, credit.used_qty - refund_qty)
                if refund_qty > 0:
                    db.add(
                        ClientPackageUsage(
                            tenant_id=tenant_id,
                            client_package_id=credit.client_package_id,
                            credit_id=credit.id,
                            change_qty=-refund_qty,
                            notes=f"Estorno de check-out da Creche #{stay.id}",
                        )
                    )
                if credit.client_package and not credit.client_package.is_active:
                    credit.client_package.is_active = True

        if stay.sale_id:
            sale = (
                db.query(Sale)
                .filter(
                    Sale.id == stay.sale_id,
                    Sale.tenant_id == tenant_id,
                    Sale.payment_method == "package",
                )
                .first()
            )
            if sale:
                db.delete(sale)
            stay.sale_id = None

        stay.covered_quantity = 0
        stay.client_package_credit_id = None

    # ---------- TASKS (RAÇÃO & REMÉDIOS) ----------
    def add_task(
        self,
        db: Session,
        tenant_id: int,
        stay_id: int,
        data: DaycareTaskCreate,
    ) -> DaycareTask:
        stay = self.repo.get_by_id(db, tenant_id, stay_id)
        if not stay:
            raise HTTPException(status_code=404, detail="Agendamento de creche não encontrado")

        task = DaycareTask(
            tenant_id=tenant_id,
            stay_id=stay.id,
            task_type=data.task_type.value,
            scheduled_time=data.scheduled_time.strip(),
            title=data.title.strip(),
            notes=data.notes,
            is_completed=False,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def update_task(
        self,
        db: Session,
        tenant_id: int,
        task_id: int,
        data: DaycareTaskUpdate,
    ) -> DaycareTask:
        task = self.repo.get_task_by_id(db, tenant_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")

        if data.task_type is not None:
            task.task_type = data.task_type.value
        if data.scheduled_time is not None:
            task.scheduled_time = data.scheduled_time.strip()
        if data.title is not None:
            task.title = data.title.strip()
        if data.notes is not None:
            task.notes = data.notes
        if data.is_completed is not None:
            task.is_completed = data.is_completed
            task.completed_at = get_brazil_now() if data.is_completed else None

        db.commit()
        db.refresh(task)
        return task

    def delete_task(
        self,
        db: Session,
        tenant_id: int,
        task_id: int,
    ) -> None:
        task = self.repo.get_task_by_id(db, tenant_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        db.delete(task)
        db.commit()

    # ---------- CARTEIRA DE SAÚDE (VACINAS / ANTIPARASITÁRIOS) ----------
    def create_health_record(
        self,
        db: Session,
        tenant_id: int,
        data: PetHealthRecordCreate,
    ) -> PetHealthRecord:
        pet = (
            db.query(Pet)
            .filter(Pet.id == data.pet_id, Pet.tenant_id == tenant_id)
            .first()
        )
        if not pet:
            raise HTTPException(status_code=404, detail="Pet não encontrado")

        record = PetHealthRecord(
            tenant_id=tenant_id,
            pet_id=data.pet_id,
            category=data.category,
            name=data.name.strip(),
            applied_at=data.applied_at,
            expires_at=data.expires_at,
            notes=data.notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_health_records_by_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ) -> List[PetHealthRecord]:
        return self.repo.list_health_records_by_pet(db, tenant_id, pet_id)

    def delete_health_record(
        self,
        db: Session,
        tenant_id: int,
        record_id: int,
    ) -> None:
        record = (
            db.query(PetHealthRecord)
            .filter(
                PetHealthRecord.id == record_id,
                PetHealthRecord.tenant_id == tenant_id,
            )
            .first()
        )
        if not record:
            raise HTTPException(status_code=404, detail="Registro de saúde não encontrado")
        db.delete(record)
        db.commit()

    # ---------- PACOTES E MENSALIDADES DA CRECHE ----------
    def list_packages(
        self,
        db: Session,
        tenant_id: int,
        only_active: bool = False,
    ) -> List[DaycarePackage]:
        query = db.query(DaycarePackage).filter(DaycarePackage.tenant_id == tenant_id)
        if only_active:
            query = query.filter(DaycarePackage.is_active == True)
        return query.order_by(DaycarePackage.id.asc()).all()

    def get_package(
        self,
        db: Session,
        tenant_id: int,
        package_id: int,
    ) -> DaycarePackage:
        pkg = (
            db.query(DaycarePackage)
            .filter(DaycarePackage.id == package_id, DaycarePackage.tenant_id == tenant_id)
            .first()
        )
        if not pkg:
            raise HTTPException(status_code=404, detail="Pacote de creche não encontrado")
        return pkg

    def create_package(
        self,
        db: Session,
        tenant_id: int,
        data: DaycarePackageCreate,
    ) -> DaycarePackage:
        pkg = DaycarePackage(
            tenant_id=tenant_id,
            name=data.name.strip(),
            price_cents=data.price_cents,
            is_monthly=data.is_monthly,
            frequency=data.frequency if data.is_monthly else None,
            days_quantity=data.days_quantity if not data.is_monthly else None,
            validity_days=data.validity_days if not data.is_monthly else None,
            is_active=data.is_active,
        )
        db.add(pkg)
        db.commit()
        db.refresh(pkg)
        return pkg

    def update_package(
        self,
        db: Session,
        tenant_id: int,
        package_id: int,
        data: DaycarePackageUpdate,
    ) -> DaycarePackage:
        pkg = self.get_package(db, tenant_id, package_id)
        if data.name is not None:
            pkg.name = data.name.strip()
        if data.price_cents is not None:
            pkg.price_cents = data.price_cents
        if data.is_monthly is not None:
            pkg.is_monthly = data.is_monthly
        if data.frequency is not None:
            pkg.frequency = data.frequency
        if data.days_quantity is not None:
            pkg.days_quantity = data.days_quantity
        if data.validity_days is not None:
            pkg.validity_days = data.validity_days
        if data.is_active is not None:
            pkg.is_active = data.is_active

        if pkg.is_monthly:
            pkg.days_quantity = None
            pkg.validity_days = None
        else:
            pkg.frequency = None

        db.commit()
        db.refresh(pkg)
        return pkg

    def delete_package(
        self,
        db: Session,
        tenant_id: int,
        package_id: int,
    ) -> None:
        pkg = self.get_package(db, tenant_id, package_id)
        db.delete(pkg)
        db.commit()
