from datetime import date
from decimal import Decimal
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from app.modules.appointments.models import Appointment, AppointmentAction, AppointmentStatus

from .repository import AppointmentRepository
from .schemas import AppointmentCreate, AppointmentUpdate, AppointmentItemCreate, AddAppointmentServiceRequest
from app.modules.pets.models import Pet
from app.modules.clients.models import Client
from app.modules.tenant_services.models import Service
from app.modules.client_packages.repository import ClientPackageRepository
from app.modules.commissions.service import CommissionService
from app.modules.tenants.models import Tenant


class AppointmentService:
    def __init__(self):
        self.repo = AppointmentRepository()
        self.credit_repo = ClientPackageRepository()
        self.commission_service = CommissionService()
    
    TRANSITIONS = {
        AppointmentStatus.PENDING: {
            AppointmentAction.CONFIRM: AppointmentStatus.CONFIRMED,
            AppointmentAction.CANCEL: AppointmentStatus.CANCELED,
            AppointmentAction.NO_SHOW: AppointmentStatus.NO_SHOW,
        },
        AppointmentStatus.CONFIRMED: {
            AppointmentAction.START: AppointmentStatus.IN_PROGRESS,
            AppointmentAction.CANCEL: AppointmentStatus.CANCELED,
            AppointmentAction.NO_SHOW: AppointmentStatus.NO_SHOW,
        },
        AppointmentStatus.IN_PROGRESS: {
            AppointmentAction.COMPLETE: AppointmentStatus.COMPLETED,
            AppointmentAction.CANCEL: AppointmentStatus.CANCELED,
        },
    }
    # ---------- CREATE ----------
    def create(
        self,
        db: Session,
        tenant_id: int,
        data: AppointmentCreate,
    ):
        # 1️⃣ Validar cliente primeiro (uma única vez)
        client = (
            db.query(Client)
            .filter(
                Client.id == data.client_id,
                Client.tenant_id == tenant_id,
            )
            .first()
        )
        if not client:
            raise HTTPException(404, "Cliente não encontrado")

        import uuid
        from datetime import timedelta
        
        recurrence_id = None
        occurrences_count = 1
        
        if data.recurrence:
            recurrence_id = str(uuid.uuid4())
            occurrences_count = data.recurrence.occurrences
            
        first_appointment = None

        for i in range(occurrences_count):
            current_scheduled_at = data.scheduled_at
            if data.recurrence and i > 0:
                if data.recurrence.frequency == 'weekly':
                    current_scheduled_at += timedelta(days=7 * i)
                elif data.recurrence.frequency == 'biweekly':
                    current_scheduled_at += timedelta(days=14 * i)
                elif data.recurrence.frequency == 'monthly':
                    # Simplified monthly recurrence: just add 28 days or use relativedelta if installed. Let's add 28 days for now or 30 days. Let's do 28 for consistency with days of week.
                    current_scheduled_at += timedelta(days=28 * i)

            # 2️⃣ Criar appointment root
            appointment = self.repo.create(
                db=db,
                tenant_id=tenant_id,
                client_id=data.client_id,
                scheduled_at=current_scheduled_at,
                notes=data.notes,
            )
            appointment.recurrence_id = recurrence_id
            appointment.recurrence_frequency = data.recurrence.frequency if data.recurrence else None
            
            if i == 0:
                first_appointment = appointment

            # 3️⃣ Para cada pet no payload
            for item in data.items:

                # Aqui reaproveitamos sua validação (apenas no primeiro iter)
                if i == 0:
                    self._validate_pet(
                        db,
                        tenant_id,
                        data.client_id,
                        item.pet_id,
                    )

                services = self._get_services(
                    db,
                    tenant_id,
                    item.service_ids,
                )

                self.repo.create_item(
                    db=db,
                    appointment=appointment,
                    pet_id=item.pet_id,
                    services=services,
                )

        # Marca onboarding como concluído no primeiro agendamento criado
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.onboarding_step != "completed":
            tenant.onboarding_step = "completed"

        db.commit()

        # Envia notificação por WhatsApp (apenas para o primeiro)
        try:
            import logging
            from app.modules.whatsapp.service import WhatsAppService
            local_logger = logging.getLogger(__name__)
            WhatsAppService().send_appointment_confirmation(db, tenant_id, first_appointment.id)
        except Exception as e:
            local_logger.error(f"Erro ao enviar notificação de agendamento por WhatsApp: {str(e)}")

        # Recarrega o primeiro agendamento com as relações prontas
        return self._attach_recurrence_info(db, self.repo.get_with_relations(db, first_appointment.id))

    # ---------- GET ----------
    def get(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
    ):
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)
        if not appointment:
            raise HTTPException(404, "Agendamento não encontrado")
        return self._attach_recurrence_info(db, appointment)

    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ):
        appts = self.repo.list_by_day(db, tenant_id, day)
        for appt in appts:
            if appt.recurrence_id and not appt.recurrence_frequency:
                appt.recurrence_frequency = "weekly"
        return appts

    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ):
        appts = self.repo.list_by_client(db, tenant_id, client_id)
        for appt in appts:
            if appt.recurrence_id and not appt.recurrence_frequency:
                appt.recurrence_frequency = "weekly"
        return appts
    
    def list_by_tenant(
        self,
        db: Session,
        tenant_id: int,
        start_date=None,
        end_date=None,
    ):
        appts = self.repo.list_by_tenant(db, tenant_id, start_date=start_date, end_date=end_date)
        for appt in appts:
            if appt.recurrence_id and not appt.recurrence_frequency:
                appt.recurrence_frequency = "weekly"
        return appts

    # ---------- UPDATE ----------
    def update(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        data: AppointmentUpdate,
        user_role: str | None = None,
        is_admin: bool = False,
    ) -> Appointment:
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id, for_update=True)
        if not appointment:
            raise HTTPException(404, "Agendamento não encontrado")
        old_scheduled_at = appointment.scheduled_at

        is_completed = (appointment.status == AppointmentStatus.COMPLETED)
        if is_completed and user_role != "owner" and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Apenas o proprietário (Owner) ou administradores podem editar agendamentos já finalizados.",
            )

        # 🔹 Atualizar campos simples
        if data.scheduled_at is not None:
            appointment.scheduled_at = data.scheduled_at

        if data.notes is not None:
            appointment.notes = data.notes

        # 🔹 Se vier items → reconstruir
        if data.items is not None:
            old_completed_snapshot = None
            if is_completed:
                old_completed_snapshot = {
                    "items": [
                        {
                            "pet_id": it.pet_id,
                            "services": [
                                {
                                    "id": s.id,
                                    "name": s.name,
                                    "price_cents": s.price_cents,
                                    "employee_id": next(
                                        (ais.employee_id for ais in it.item_services if ais.service_id == s.id),
                                        None,
                                    ),
                                    "coverage": next(
                                        (c for c in it.coverages if c.service_id == s.id),
                                        None,
                                    ),
                                }
                                for s in it.services
                            ],
                        }
                        for it in appointment.items
                    ]
                }

            existing_pet_ids = {it.pet_id for it in appointment.items}

            # Preserva profissionais atribuídos aos serviços existentes
            existing_emp_map: dict[tuple[int, int], int | None] = {}
            for it in appointment.items:
                for ais in getattr(it, "item_services", []):
                    if ais.employee_id:
                        existing_emp_map[(it.pet_id, ais.service_id)] = ais.employee_id

            # Remove todos os items antigos
            self.repo.delete_items(db, appointment)

            # Recria baseado no payload
            for item in data.items:

                self._validate_pet(
                    db,
                    tenant_id,
                    appointment.client_id,
                    item.pet_id,
                    allow_deceased=(item.pet_id in existing_pet_ids),
                )

                services = self._get_services(
                    db,
                    tenant_id,
                    item.service_ids,
                )

                created_item = self.repo.create_item(
                    db=db,
                    appointment=appointment,
                    pet_id=item.pet_id,
                    services=services,
                )

                # Restaura funcionário já atribuído se este pet e serviço já tinham profissional
                if existing_emp_map:
                    from app.modules.appointments.models import AppointmentItemService
                    for s in services:
                        old_emp_id = existing_emp_map.get((item.pet_id, s.id))
                        if old_emp_id:
                            db.query(AppointmentItemService).filter(
                                AppointmentItemService.appointment_item_id == created_item.id,
                                AppointmentItemService.service_id == s.id,
                            ).update({"employee_id": old_emp_id}, synchronize_session=False)

            db.flush()
            db.expire(appointment, ["items"])

            # Se for um agendamento finalizado, executa a sincronização profunda de pacotes, vendas, extratos e comissões
            if is_completed and old_completed_snapshot:
                self._sync_completed_appointment(
                    db,
                    tenant_id,
                    appointment,
                    old_completed_snapshot,
                )

        if not data.update_all_future:
            # Se for alterar APENAS este, desvincula da série de recorrência para não afetar os outros
            if appointment.recurrence_id:
                appointment.recurrence_id = None
                appointment.recurrence_frequency = None
        else:
            # Alterar este e TODOS os futuros
            import uuid
            if data.remove_recurrence:
                # O usuário desmarcou a recorrência: remove recorrência deste e dos futuros
                if appointment.recurrence_id:
                    future_appointments = (
                        db.query(Appointment)
                        .filter(
                            Appointment.tenant_id == tenant_id,
                            Appointment.recurrence_id == appointment.recurrence_id,
                            Appointment.scheduled_at > old_scheduled_at,
                            Appointment.id != appointment.id,
                        )
                        .all()
                    )
                    for future_appt in future_appointments:
                        if not future_appt.is_paid and future_appt.status in [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]:
                            db.delete(future_appt)
                        else:
                            future_appt.recurrence_id = None
                            future_appt.recurrence_frequency = None

                appointment.recurrence_id = None
                appointment.recurrence_frequency = None

            elif data.recurrence is not None:
                new_freq = data.recurrence.frequency
                new_occurrences = data.recurrence.occurrences

                is_new_series = not appointment.recurrence_id
                old_freq = appointment.recurrence_frequency
                if not old_freq and not is_new_series:
                    self._attach_recurrence_info(db, appointment)
                    old_freq = appointment.recurrence_frequency

                freq_changed = (old_freq != new_freq)

                if is_new_series:
                    recurrence_id = str(uuid.uuid4())
                    appointment.recurrence_id = recurrence_id
                    appointment.recurrence_frequency = new_freq
                else:
                    recurrence_id = appointment.recurrence_id
                    appointment.recurrence_frequency = new_freq

                if is_new_series or freq_changed:
                    # Deletar futuros agendamentos pendentes da série antiga se existirem
                    if not is_new_series:
                        old_future_appts = (
                            db.query(Appointment)
                            .filter(
                                Appointment.tenant_id == tenant_id,
                                Appointment.recurrence_id == recurrence_id,
                                Appointment.scheduled_at > old_scheduled_at,
                                Appointment.id != appointment.id,
                            )
                            .all()
                        )
                        for fa in old_future_appts:
                            if not fa.is_paid and fa.status in [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]:
                                db.delete(fa)
                        db.flush()

                    # Obter items para replicar nos futuros
                    items_payload = data.items
                    if items_payload is None:
                        items_payload = [
                            AppointmentItemCreate(
                                pet_id=it.pet_id,
                                service_ids=[svc.id for svc in it.services],
                            )
                            for it in appointment.items
                        ]

                    # Criar new_occurrences - 1 agendamentos futuros
                    for i in range(1, new_occurrences):
                        future_scheduled_at = self._calculate_next_scheduled_at(appointment.scheduled_at, new_freq, i)
                        future_appt = self.repo.create(
                            db=db,
                            tenant_id=tenant_id,
                            client_id=appointment.client_id,
                            scheduled_at=future_scheduled_at,
                            notes=appointment.notes,
                        )
                        future_appt.recurrence_id = recurrence_id
                        future_appt.recurrence_frequency = new_freq

                        for item in items_payload:
                            services = self._get_services(
                                db,
                                tenant_id,
                                item.service_ids,
                            )
                            self.repo.create_item(
                                db=db,
                                appointment=future_appt,
                                pet_id=item.pet_id,
                                services=services,
                            )
                else:
                    # Frequência não mudou: desloca e atualiza os existentes
                    time_delta = (data.scheduled_at - old_scheduled_at) if data.scheduled_at is not None else None

                    future_appointments = (
                        db.query(Appointment)
                        .filter(
                            Appointment.tenant_id == tenant_id,
                            Appointment.recurrence_id == appointment.recurrence_id,
                            Appointment.scheduled_at > old_scheduled_at,
                            Appointment.id != appointment.id,
                            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                        )
                        .order_by(Appointment.scheduled_at.asc())
                        .with_for_update(of=Appointment)
                        .all()
                    )

                    for future_appt in future_appointments:
                        if time_delta is not None:
                            future_appt.scheduled_at = future_appt.scheduled_at + time_delta
                        if data.notes is not None:
                            future_appt.notes = data.notes
                        if data.items is not None:
                            existing_future_pet_ids = {it.pet_id for it in future_appt.items}
                            self.repo.delete_items(db, future_appt)
                            for item in data.items:
                                self._validate_pet(
                                    db,
                                    tenant_id,
                                    future_appt.client_id,
                                    item.pet_id,
                                    allow_deceased=(item.pet_id in existing_future_pet_ids),
                                )
                                services = self._get_services(
                                    db,
                                    tenant_id,
                                    item.service_ids,
                                )
                                self.repo.create_item(
                                    db=db,
                                    appointment=future_appt,
                                    pet_id=item.pet_id,
                                    services=services,
                                )

                    # Ajustar quantidade de ocorrências se mudou
                    current_count = 1 + len(future_appointments)
                    if new_occurrences > current_count:
                        items_payload = data.items
                        if items_payload is None:
                            items_payload = [
                                AppointmentItemCreate(
                                    pet_id=it.pet_id,
                                    service_ids=[svc.id for svc in it.services],
                                )
                                for it in appointment.items
                            ]
                        for i in range(current_count, new_occurrences):
                            future_scheduled_at = self._calculate_next_scheduled_at(appointment.scheduled_at, new_freq, i)
                            future_appt = self.repo.create(
                                db=db,
                                tenant_id=tenant_id,
                                client_id=appointment.client_id,
                                scheduled_at=future_scheduled_at,
                                notes=appointment.notes,
                            )
                            future_appt.recurrence_id = recurrence_id
                            future_appt.recurrence_frequency = new_freq

                            for item in items_payload:
                                services = self._get_services(
                                    db,
                                    tenant_id,
                                    item.service_ids,
                                )
                                self.repo.create_item(
                                    db=db,
                                    appointment=future_appt,
                                    pet_id=item.pet_id,
                                    services=services,
                                )
                    elif new_occurrences < current_count:
                        excess = current_count - new_occurrences
                        to_delete = future_appointments[-excess:]
                        for fa in to_delete:
                            if not fa.is_paid and fa.status in [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]:
                                db.delete(fa)

            elif appointment.recurrence_id:
                # Nenhum data.recurrence foi enviado, mas update_all_future foi marcado: replica horário/items
                time_delta = (data.scheduled_at - old_scheduled_at) if data.scheduled_at is not None else None

                future_appointments = (
                    db.query(Appointment)
                    .filter(
                        Appointment.tenant_id == tenant_id,
                        Appointment.recurrence_id == appointment.recurrence_id,
                        Appointment.scheduled_at > old_scheduled_at,
                        Appointment.id != appointment.id,
                        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                    )
                    .order_by(Appointment.scheduled_at.asc())
                    .with_for_update(of=Appointment)
                    .all()
                )

                for future_appt in future_appointments:
                    if time_delta is not None:
                        future_appt.scheduled_at = future_appt.scheduled_at + time_delta

                    if data.notes is not None:
                        future_appt.notes = data.notes

                    if data.items is not None:
                        existing_future_pet_ids = {it.pet_id for it in future_appt.items}
                        self.repo.delete_items(db, future_appt)
                        for item in data.items:
                            self._validate_pet(
                                db,
                                tenant_id,
                                future_appt.client_id,
                                item.pet_id,
                                allow_deceased=(item.pet_id in existing_future_pet_ids),
                            )
                            services = self._get_services(
                                db,
                                tenant_id,
                                item.service_ids,
                            )
                            self.repo.create_item(
                                db=db,
                                appointment=future_appt,
                                pet_id=item.pet_id,
                                services=services,
                            )

        db.commit()

        return self._attach_recurrence_info(db, self.repo.get_with_relations(db, appointment.id))
        
    def assign_employees(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        assignments: list,
    ):
        appointment = self.get(db, tenant_id, appointment_id)
        result = self.repo.assign_employees(db, appointment.id, assignments)

        # Se o agendamento já estiver finalizado, sincroniza os SaleItems e as comissões
        if appointment.status == AppointmentStatus.COMPLETED:
            from app.modules.sales.models import Sale, SaleItem
            from app.modules.commissions.models import CommissionEntry

            for assignment in assignments:
                sale_items = (
                    db.query(SaleItem)
                    .join(Sale)
                    .filter(
                        Sale.tenant_id == tenant_id,
                        Sale.status == "completed",
                        SaleItem.item_type == "service",
                        SaleItem.item_id == assignment.service_id,
                        (SaleItem.appointment_id == appointment.id) | (Sale.appointment_id == appointment.id),
                    )
                    .all()
                )
                for si in sale_items:
                    si.employee_id = assignment.employee_id
                    db.query(CommissionEntry).filter(
                        CommissionEntry.sale_item_id == si.id
                    ).delete(synchronize_session=False)

                    if assignment.employee_id:
                        try:
                            subtotal_price = Decimal(str(si.unit_price)) if si.subtotal == 0 else Decimal(str(si.subtotal))
                            self.commission_service.generate_entry(
                                db=db,
                                tenant_id=tenant_id,
                                sale_id=si.sale_id,
                                sale_item_id=si.id,
                                employee_id=assignment.employee_id,
                                service_id=assignment.service_id,
                                item_type="service",
                                subtotal=subtotal_price,
                                ref_date=appointment.scheduled_at.date(),
                                appointment_item_id=assignment.appointment_item_id,
                            )
                        except Exception:
                            pass
            db.commit()

        return result

    # ---------- DELETE ----------
    def delete(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
    ):
        appointment = self.get(db, tenant_id, appointment_id)
        self.repo.delete(db, appointment)

    # ---------- helpers ----------
    def _sync_completed_appointment(
        self,
        db: Session,
        tenant_id: int,
        appointment: Appointment,
        snapshot: dict,
    ):
        from app.modules.client_packages.models import ClientPackageCredit, ClientPackageUsage
        from app.modules.sales.models import Sale, SaleItem, Comanda, ComandaItem
        from app.modules.commissions.models import CommissionEntry
        from app.modules.appointments.models import AppointmentItemService

        db.flush()
        db.expire(appointment)
        appointment_full = self.repo.get_with_relations(db, appointment.id)

        # 1. Mapeamento dos serviços antigos: (pet_id, service_id) -> info
        old_services_map: dict[tuple[int, int], dict] = {}
        for it in snapshot.get("items", []):
            pet_id = it["pet_id"]
            for s in it["services"]:
                old_services_map[(pet_id, s["id"])] = s

        # 2. Mapeamento dos novos items recém-criados: (pet_id, service_id) -> (item, service)
        new_items_by_pair: dict[tuple[int, int], tuple[any, any]] = {}
        for it in appointment_full.items:
            for s in it.services:
                new_items_by_pair[(it.pet_id, s.id)] = (it, s)

        # 3. Preservar atribuições de funcionários se o serviço já existia e tinha funcionário
        for (pet_id, s_id), (new_it, new_s) in new_items_by_pair.items():
            if (pet_id, s_id) in old_services_map:
                old_emp_id = old_services_map[(pet_id, s_id)].get("employee_id")
                if old_emp_id:
                    db.query(AppointmentItemService).filter(
                        AppointmentItemService.appointment_item_id == new_it.id,
                        AppointmentItemService.service_id == s_id,
                    ).update({"employee_id": old_emp_id}, synchronize_session=False)

        db.flush()
        appointment_full = self.repo.get_with_relations(db, appointment.id)

        item_emp_maps = {
            item.id: {ais.service_id: ais.employee_id for ais in item.item_services}
            for item in appointment_full.items
        }

        # 4. PACOTES: Devolver créditos de serviços que foram removidos
        for (pet_id, s_id), old_info in old_services_map.items():
            if (pet_id, s_id) not in new_items_by_pair:
                cov = old_info.get("coverage")
                if cov and cov.client_package_credit_id:
                    credit = db.query(ClientPackageCredit).filter(
                        ClientPackageCredit.id == cov.client_package_credit_id
                    ).first()
                    if credit:
                        credit.used_qty = max(0, credit.used_qty - 1)
                        usage = ClientPackageUsage(
                            tenant_id=tenant_id,
                            client_package_id=credit.client_package_id,
                            credit_id=credit.id,
                            change_qty=-1,
                            notes=f"Estorno por edição do agendamento #{appointment.id}",
                        )
                        db.add(usage)
                        client_pkg = credit.client_package
                        if client_pkg and not client_pkg.is_active:
                            client_pkg.is_active = True
                            db.add(client_pkg)

        # 5. PACOTES: Manter ou consumir créditos para os novos pares
        new_covered_pairs: set[tuple[int, int]] = set()
        for (pet_id, s_id), (it, s) in new_items_by_pair.items():
            old_info = old_services_map.get((pet_id, s_id))
            cov = old_info.get("coverage") if old_info else None

            if cov and cov.client_package_credit_id:
                # Mantém a cobertura existente
                self.repo.create_coverage(
                    db,
                    appointment_item_id=it.id,
                    service_id=s.id,
                    client_package_credit_id=cov.client_package_credit_id,
                )
                new_covered_pairs.add((it.id, s.id))
            else:
                # Novo serviço adicionado: verifica se há crédito de pacote ativo
                credit = self.credit_repo.find_active_credit(db, tenant_id, pet_id, s.id)
                if credit:
                    notes = f"Consumido via edição do agendamento #{appointment.id}"
                    self.credit_repo.consume_credit(db, credit, notes=notes)
                    self.repo.create_coverage(
                        db,
                        appointment_item_id=it.id,
                        service_id=s.id,
                        client_package_credit_id=credit.id,
                    )
                    new_covered_pairs.add((it.id, s.id))

        db.flush()

        # 6. Sincronizar Package Sale (R$ 0)
        covered_services = [
            (it, s)
            for it in appointment_full.items
            for s in it.services
            if (it.id, s.id) in new_covered_pairs
        ]

        # 6. Identifica vendas e comandas existentes
        uncovered_services = [
            (it, s)
            for it in appointment_full.items
            for s in it.services
            if (it.id, s.id) not in new_covered_pairs
        ]

        package_sale = db.query(Sale).filter(
            Sale.tenant_id == tenant_id,
            Sale.appointment_id == appointment.id,
            Sale.payment_method == "package",
        ).first()

        pos_sale = db.query(Sale).filter(
            Sale.tenant_id == tenant_id,
            Sale.payment_method != "package",
            Sale.status == "completed",
            (Sale.appointment_id == appointment.id) | (
                Sale.items.any(SaleItem.appointment_id == appointment.id)
            )
        ).first()

        if pos_sale:
            # Se já há venda paga do PDV, remove qualquer package_sale avulsa duplicada
            if package_sale:
                for old_si in list(package_sale.items):
                    db.query(CommissionEntry).filter(CommissionEntry.sale_item_id == old_si.id).delete(synchronize_session=False)
                db.delete(package_sale)
                db.flush()

            # Remove itens de serviço do agendamento da pos_sale para recriá-los sincronizados
            for si in list(pos_sale.items):
                if si.appointment_id == appointment.id or (si.appointment_id is None and pos_sale.appointment_id == appointment.id and si.item_type == "service"):
                    db.query(CommissionEntry).filter(CommissionEntry.sale_item_id == si.id).delete(synchronize_session=False)
                    pos_sale.items.remove(si)
                    db.delete(si)
            db.flush()

            # Adiciona serviços cobertos por pacote com subtotal 0,00 na pos_sale
            for it, s in covered_services:
                emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                real_price = Decimal(s.price_cents) / Decimal("100")
                sale_item = SaleItem(
                    sale_id=pos_sale.id,
                    item_type="service",
                    item_id=s.id,
                    name=f"{s.name} (via pacote)",
                    quantity=1,
                    unit_price=real_price,
                    subtotal=Decimal("0"),
                    employee_id=emp_id,
                    appointment_id=appointment_full.id,
                )
                db.add(sale_item)
                if "items" in pos_sale.__dict__:
                    pos_sale.items.append(sale_item)
                db.flush()

                if emp_id:
                    try:
                        self.commission_service.generate_entry(
                            db=db,
                            tenant_id=tenant_id,
                            sale_id=pos_sale.id,
                            sale_item_id=sale_item.id,
                            employee_id=emp_id,
                            service_id=s.id,
                            item_type="service",
                            subtotal=real_price,
                            ref_date=appointment_full.scheduled_at.date(),
                            appointment_item_id=it.id,
                        )
                    except Exception:
                        pass

            # Adiciona serviços avulsos na pos_sale
            for it, s in uncovered_services:
                emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                price = Decimal(s.price_cents) / Decimal("100")
                sale_item = SaleItem(
                    sale_id=pos_sale.id,
                    item_type="service",
                    item_id=s.id,
                    name=s.name,
                    quantity=1,
                    unit_price=price,
                    subtotal=price,
                    employee_id=emp_id,
                    appointment_id=appointment_full.id,
                )
                db.add(sale_item)
                if "items" in pos_sale.__dict__:
                    pos_sale.items.append(sale_item)
                db.flush()

                if emp_id:
                    try:
                        self.commission_service.generate_entry(
                            db=db,
                            tenant_id=tenant_id,
                            sale_id=pos_sale.id,
                            sale_item_id=sale_item.id,
                            employee_id=emp_id,
                            service_id=s.id,
                            item_type="service",
                            subtotal=price,
                            ref_date=appointment_full.scheduled_at.date(),
                            appointment_item_id=it.id,
                        )
                    except Exception:
                        pass

            db.flush()
            current_sale_items = db.query(SaleItem).filter(SaleItem.sale_id == pos_sale.id).all()
            new_subtotal = sum(Decimal(str(si.subtotal)) for si in current_sale_items)
            pos_sale.total_amount = float(max(Decimal("0"), new_subtotal - Decimal(str(pos_sale.discount_amount))))
            if pos_sale.payments and len(pos_sale.payments) == 1:
                pos_sale.payments[0].amount = pos_sale.total_amount
            elif pos_sale.payments:
                current_payments_sum = sum(Decimal(str(p.amount)) for p in pos_sale.payments)
                diff = Decimal(str(pos_sale.total_amount)) - current_payments_sum
                if diff != Decimal("0"):
                    pos_sale.payments[0].amount = float(Decimal(str(pos_sale.payments[0].amount)) + diff)
        else:
            # Agendamento ainda não pago via PDV
            from sqlalchemy import or_
            open_comandas = db.query(Comanda).filter(
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
                or_(
                    Comanda.appointment_id == appointment.id,
                    Comanda.client_id == appointment.client_id,
                )
            ).all()

            if uncovered_services or open_comandas:
                # Há comanda ou itens a pagar: remove package_sale para que tudo vá para o Caixa
                if package_sale:
                    for old_si in list(package_sale.items):
                        db.query(CommissionEntry).filter(CommissionEntry.sale_item_id == old_si.id).delete(synchronize_session=False)
                    db.delete(package_sale)
                    db.flush()

                for comanda in open_comandas:
                    for ci in list(comanda.items):
                        if ci.appointment_id == appointment.id or (ci.appointment_id is None and comanda.appointment_id == appointment.id and ci.item_type == "service"):
                            comanda.items.remove(ci)
                            db.delete(ci)
                    db.flush()

                    for it, s in covered_services:
                        emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                        real_price = float(Decimal(s.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=s.id,
                            name=f"{s.name} (via pacote)",
                            quantity=1,
                            unit_price=real_price,
                            subtotal=0.0,
                            employee_id=emp_id,
                            pet_ids=[it.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

                    for it, s in uncovered_services:
                        emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                        price = float(Decimal(s.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=s.id,
                            name=s.name,
                            quantity=1,
                            unit_price=price,
                            subtotal=price,
                            employee_id=emp_id,
                            pet_ids=[it.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

                    db.flush()
                    remaining_subtotal = sum(ci.subtotal for ci in comanda.items)
                    comanda.total_amount = max(0.0, float(Decimal(str(remaining_subtotal)) - Decimal(str(comanda.discount_amount))))
                    if not comanda.items:
                        db.delete(comanda)

                if uncovered_services and not open_comandas:
                    extra_total = sum(Decimal(s.price_cents) / Decimal("100") for _, s in uncovered_services)
                    comanda = Comanda(
                        tenant_id=tenant_id,
                        client_id=appointment_full.client_id,
                        appointment_id=appointment_full.id,
                        status="open",
                        total_amount=float(extra_total),
                        discount_amount=0.0,
                    )
                    db.add(comanda)
                    db.flush()

                    for it, s in covered_services:
                        emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                        real_price = float(Decimal(s.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=s.id,
                            name=f"{s.name} (via pacote)",
                            quantity=1,
                            unit_price=real_price,
                            subtotal=0.0,
                            employee_id=emp_id,
                            pet_ids=[it.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

                    for it, s in uncovered_services:
                        emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                        price = float(Decimal(s.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=s.id,
                            name=s.name,
                            quantity=1,
                            unit_price=price,
                            subtotal=price,
                            employee_id=emp_id,
                            pet_ids=[it.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

            elif covered_services:
                # 100% pacote sem extras nem comanda
                if not package_sale:
                    package_sale = Sale(
                        tenant_id=tenant_id,
                        client_id=appointment_full.client_id,
                        appointment_id=appointment_full.id,
                        total_amount=Decimal("0"),
                        payment_method="package",
                        status="completed",
                    )
                    db.add(package_sale)
                    db.flush()

                for old_si in list(package_sale.items):
                    db.query(CommissionEntry).filter(CommissionEntry.sale_item_id == old_si.id).delete(synchronize_session=False)
                    package_sale.items.remove(old_si)
                    db.delete(old_si)
                db.flush()

                for it, s in covered_services:
                    emp_id = item_emp_maps.get(it.id, {}).get(s.id)
                    real_price = Decimal(s.price_cents) / Decimal("100")
                    sale_item = SaleItem(
                        sale_id=package_sale.id,
                        item_type="service",
                        item_id=s.id,
                        name=s.name,
                        quantity=1,
                        unit_price=real_price,
                        subtotal=Decimal("0"),
                        employee_id=emp_id,
                        appointment_id=appointment_full.id,
                    )
                    db.add(sale_item)
                    db.flush()

                    if emp_id:
                        try:
                            self.commission_service.generate_entry(
                                db=db,
                                tenant_id=tenant_id,
                                sale_id=package_sale.id,
                                sale_item_id=sale_item.id,
                                employee_id=emp_id,
                                service_id=s.id,
                                item_type="service",
                                subtotal=real_price,
                                ref_date=appointment_full.scheduled_at.date(),
                                appointment_item_id=it.id,
                            )
                        except Exception:
                            pass
            elif package_sale:
                for old_si in list(package_sale.items):
                    db.query(CommissionEntry).filter(CommissionEntry.sale_item_id == old_si.id).delete(synchronize_session=False)
                db.delete(package_sale)

        db.commit()

    def _calculate_next_scheduled_at(self, base_date, frequency: str, index: int):
        from datetime import timedelta
        if frequency == 'weekly':
            return base_date + timedelta(days=7 * index)
        elif frequency == 'biweekly':
            return base_date + timedelta(days=14 * index)
        elif frequency == 'monthly':
            return base_date + timedelta(days=28 * index)
        return base_date + timedelta(days=7 * index)

    def _attach_recurrence_info(self, db: Session, appointment: Appointment | None) -> Appointment | None:
        if not appointment or not appointment.recurrence_id:
            if appointment:
                appointment.recurrence = None
            return appointment

        frequency = appointment.recurrence_frequency
        if not frequency:
            # Fallback para deduzir frequência em agendamentos legados
            series = (
                db.query(Appointment.scheduled_at)
                .filter(
                    Appointment.tenant_id == appointment.tenant_id,
                    Appointment.recurrence_id == appointment.recurrence_id,
                )
                .order_by(Appointment.scheduled_at.asc())
                .limit(2)
                .all()
            )
            if len(series) >= 2:
                days = abs((series[1][0].date() - series[0][0].date()).days)
                if 5 <= days <= 9:
                    frequency = "weekly"
                elif 12 <= days <= 16:
                    frequency = "biweekly"
                else:
                    frequency = "monthly"
            else:
                frequency = "weekly"
            appointment.recurrence_frequency = frequency

        count = (
            db.query(Appointment)
            .filter(
                Appointment.tenant_id == appointment.tenant_id,
                Appointment.recurrence_id == appointment.recurrence_id,
                Appointment.scheduled_at >= appointment.scheduled_at,
                Appointment.status != AppointmentStatus.CANCELED,
            )
            .count()
        )

        appointment.recurrence = {
            "frequency": frequency,
            "occurrences": max(2, count),
        }
        return appointment
    def _validate_pet(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
        allow_deceased: bool = False,
    ):
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
            raise HTTPException(404, "Pet não encontrado")
        if pet.is_deceased and not allow_deceased:
            raise HTTPException(400, f"Não é possível agendar para o pet '{pet.name}', pois consta como óbito.")
        
    def _get_services(
        self,
        db: Session,
        tenant_id: int,
        service_ids: list[int],
    ) -> list[Service]:
        services = (
            db.query(Service)
            .filter(
                Service.id.in_(service_ids),
                Service.tenant_id == tenant_id,
                Service.is_active,
            )
            .all()
        )

        if len(services) != len(service_ids):
            raise HTTPException(
                400, "Um ou mais serviços são inválidos"
            )

        return services
    
    def apply_action(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        action: AppointmentAction,
        cancel_all_future: bool = False,
        by_whatsapp: bool = False,
    ):
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)

        if not appointment:
            return ("Agendamento não encontrado")

        current_status = appointment.status

        if current_status not in self.TRANSITIONS:
            raise HTTPException(
                status_code=400,
                detail="Ação inválida para o status atual",
            )

        if action not in self.TRANSITIONS[current_status]:
            raise HTTPException(
                status_code=400,
                detail=f"Ação '{action}' inválida para status '{current_status}'",
            )

        new_status = self.TRANSITIONS[current_status][action]
        appointment.status = new_status

        result = self.repo.save_action(db, appointment)

        if action == AppointmentAction.CANCEL and cancel_all_future and appointment.recurrence_id:
            from app.modules.appointments.models import Appointment
            future_appointments = db.query(Appointment).filter(
                Appointment.tenant_id == tenant_id,
                Appointment.recurrence_id == appointment.recurrence_id,
                Appointment.scheduled_at > appointment.scheduled_at,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
            ).all()
            for future_appt in future_appointments:
                future_appt.status = AppointmentStatus.CANCELED
                self.repo.save_action(db, future_appt)

        if action == AppointmentAction.CANCEL and not by_whatsapp:
            try:
                db.commit()
                from app.modules.whatsapp.service import WhatsAppService
                WhatsAppService().send_whatsapp_notification(db, tenant_id, appointment.id, "appointment_canceled")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Erro ao notificar cancelamento por WhatsApp: {str(e)}")

        # Ao completar, desconta créditos de pacotes e registra coverages (FIFO)
        if action == AppointmentAction.COMPLETE:
            appointment_full = self.repo.get_with_relations(db, appointment.id)

            # Captura employee_id por serviço antes de qualquer modificação
            item_emp_maps = {
                item.id: {ais.service_id: ais.employee_id for ais in item.item_services}
                for item in appointment_full.items
            }

            # Consome créditos e registra coverages; rastreia quais pares foram cobertos
            covered_pairs: set[tuple[int, int]] = set()
            for item in appointment_full.items:
                for service in item.services:
                    credit = self.credit_repo.find_active_credit(
                        db, tenant_id, item.pet_id, service.id
                    )
                    if credit:
                        notes = f"Consumido via agendamento - Pet: {item.pet.name}" if item.pet else "Consumido via agendamento"
                        self.credit_repo.consume_credit(db, credit, notes=notes)
                        self.repo.create_coverage(
                            db,
                            appointment_item_id=item.id,
                            service_id=service.id,
                            client_package_credit_id=credit.id,
                        )
                        covered_pairs.add((item.id, service.id))

            db.flush()

            # Coleta TODOS os serviços cobertos por pacote
            covered_services = [
                (item, service)
                for item in appointment_full.items
                for service in item.services
                if (item.id, service.id) in covered_pairs
            ]

            # Coleta serviços não cobertos por pacote
            uncovered_services = [
                (item, service)
                for item in appointment_full.items
                for service in item.services
                if (item.id, service.id) not in covered_pairs
            ]

            from app.modules.sales.models import Sale, SaleItem, Comanda, ComandaItem

            # Verifica se o agendamento já possui uma venda de PDV concluída
            pos_sale = db.query(Sale).filter(
                Sale.tenant_id == tenant_id,
                Sale.payment_method != "package",
                Sale.status == "completed",
                (Sale.appointment_id == appointment.id) | (
                    Sale.items.any(SaleItem.appointment_id == appointment.id)
                )
            ).first()

            if not pos_sale:
                existing_comanda = db.query(Comanda).filter(
                    Comanda.client_id == appointment_full.client_id,
                    Comanda.tenant_id == tenant_id,
                    Comanda.status == "open",
                ).first()

                # Se há serviços não cobertos (ou comanda aberta), tudo vai para a comanda unificada
                if uncovered_services or existing_comanda:
                    extra_total = sum(Decimal(service.price_cents) / Decimal("100") for _, service in uncovered_services)

                    if not existing_comanda:
                        comanda = Comanda(
                            tenant_id=tenant_id,
                            client_id=appointment_full.client_id,
                            appointment_id=appointment_full.id,
                            status="open",
                            total_amount=float(extra_total),
                            discount_amount=0.0,
                        )
                        db.add(comanda)
                        db.flush()
                    else:
                        comanda = existing_comanda
                        comanda.total_amount = float(Decimal(str(comanda.total_amount)) + extra_total)
                        if not comanda.appointment_id:
                            comanda.appointment_id = appointment_full.id

                    # Inclui serviços cobertos por pacote na comanda com subtotal 0,00
                    for item, service in covered_services:
                        emp_id = item_emp_maps[item.id].get(service.id)
                        real_price = float(Decimal(service.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=service.id,
                            name=f"{service.name} (via pacote)",
                            quantity=1,
                            unit_price=real_price,
                            subtotal=0.0,
                            employee_id=emp_id,
                            pet_ids=[item.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

                    # Inclui serviços não cobertos por pacote com preço normal
                    for item, service in uncovered_services:
                        emp_id = item_emp_maps[item.id].get(service.id)
                        price = float(Decimal(service.price_cents) / Decimal("100"))
                        c_item = ComandaItem(
                            comanda_id=comanda.id,
                            item_type="service",
                            item_id=service.id,
                            name=service.name,
                            quantity=1,
                            unit_price=price,
                            subtotal=price,
                            employee_id=emp_id,
                            pet_ids=[item.pet_id],
                            unit="UN",
                            appointment_id=appointment_full.id,
                        )
                        db.add(c_item)

                elif covered_services:
                    # Agendamento 100% pacote sem extras nem comanda: conclui direto com package_sale
                    package_sale = Sale(
                        tenant_id=tenant_id,
                        client_id=appointment_full.client_id,
                        appointment_id=appointment_full.id,
                        total_amount=Decimal("0"),
                        payment_method="package",
                        status="completed",
                    )
                    db.add(package_sale)
                    db.flush()

                    for item, service in covered_services:
                        employee_id = item_emp_maps[item.id].get(service.id)
                        real_price = Decimal(service.price_cents) / Decimal("100")
                        sale_item = SaleItem(
                            sale_id=package_sale.id,
                            item_type="service",
                            item_id=service.id,
                            name=service.name,
                            quantity=1,
                            unit_price=real_price,
                            subtotal=Decimal("0"),
                            employee_id=employee_id,
                            appointment_id=appointment_full.id,
                        )
                        db.add(sale_item)
                        db.flush()

                        if employee_id:
                            try:
                                self.commission_service.generate_entry(
                                    db=db,
                                    tenant_id=tenant_id,
                                    sale_id=package_sale.id,
                                    sale_item_id=sale_item.id,
                                    employee_id=employee_id,
                                    service_id=service.id,
                                    item_type="service",
                                    subtotal=real_price,
                                    ref_date=appointment_full.scheduled_at.date(),
                                    appointment_item_id=item.id,
                                )
                            except Exception:
                                pass

            db.commit()

            # Envia notificação de Pet Pronto por WhatsApp
            try:
                import logging
                from app.modules.whatsapp.service import WhatsAppService
                WhatsAppService().send_whatsapp_notification(db, tenant_id, appointment.id, "pet_ready")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Erro ao notificar que o pet está pronto: {str(e)}")

            # Aviso não-bloqueante se algum serviço estiver sem funcionário
            missing_services: list[str] = []
            for item in appointment_full.items:
                emp_map = item_emp_maps[item.id]
                for svc in item.services:
                    if not emp_map.get(svc.id):
                        missing_services.append(svc.name)

            # Recarrega com as coverages para o response final
            result = self.repo.get_with_relations(db, appointment.id)
            if missing_services:
                unique_missing = list(dict.fromkeys(missing_services))
                result.warnings = [
                    f"Atenção: serviços sem funcionário vinculado: {', '.join(unique_missing)}"
                ]

        return result

    def list_open_invoices(
        self,
        db: Session,
        tenant_id: int,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ):
        items, total = self.repo.list_open_invoices(db, tenant_id, limit, offset, search)
        return {"items": items, "total": total}

    def list_highlighted_days(
        self,
        db: Session,
        tenant_id: int,
        start_date=None,
        end_date=None,
    ) -> list[date]:
        return self.repo.list_highlighted_days(db, tenant_id, start_date=start_date, end_date=end_date)

    def add_service(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        data: AddAppointmentServiceRequest,
    ) -> Appointment:
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id, for_update=True)
        if not appointment:
            raise HTTPException(404, "Agendamento não encontrado")

        if appointment.is_paid:
            raise HTTPException(400, "Não é possível adicionar serviço a um agendamento já pago no caixa.")

        if appointment.status in [AppointmentStatus.CANCELED, AppointmentStatus.NO_SHOW]:
            raise HTTPException(400, "Não é possível adicionar serviço a um agendamento cancelado ou com não comparecimento.")

        # 1. Validar serviço
        service = db.query(Service).filter(
            Service.id == data.service_id,
            Service.tenant_id == tenant_id,
            Service.is_active == True,
        ).first()
        if not service:
            raise HTTPException(404, "Serviço não encontrado ou inativo")

        # 2. Localizar ou criar item para o pet
        target_item = next((it for it in appointment.items if it.pet_id == data.pet_id), None)
        if not target_item:
            existing_pet_ids = {it.pet_id for it in appointment.items}
            self._validate_pet(
                db,
                tenant_id,
                appointment.client_id,
                data.pet_id,
                allow_deceased=(data.pet_id in existing_pet_ids),
            )
            target_item = self.repo.create_item(
                db=db,
                appointment=appointment,
                pet_id=data.pet_id,
                services=[service],
            )
            db.flush()
        else:
            if not any(s.id == service.id for s in target_item.services):
                target_item.services.append(service)
                db.flush()

        # 3. Vincular funcionário se fornecido
        if data.employee_id:
            from app.modules.appointments.models import AppointmentItemService
            db.query(AppointmentItemService).filter(
                AppointmentItemService.appointment_item_id == target_item.id,
                AppointmentItemService.service_id == service.id,
            ).update({"employee_id": data.employee_id}, synchronize_session=False)

        # 4. Se o agendamento já estava COMPLETED, sincroniza com comanda aberta se houver
        if appointment.status == AppointmentStatus.COMPLETED:
            from app.modules.sales.models import Comanda, ComandaItem
            comanda = db.query(Comanda).filter(
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
                or_(
                    Comanda.appointment_id == appointment.id,
                    Comanda.client_id == appointment.client_id,
                )
            ).first()
            if comanda:
                real_price = float(Decimal(service.price_cents) / Decimal("100"))
                c_item = ComandaItem(
                    comanda_id=comanda.id,
                    item_type="service",
                    item_id=service.id,
                    name=service.name,
                    quantity=1,
                    unit_price=real_price,
                    subtotal=real_price,
                    employee_id=data.employee_id,
                    pet_ids=[data.pet_id],
                    unit="UN",
                    appointment_id=appointment.id,
                )
                db.add(c_item)
                comanda.total_amount = max(0.0, float(Decimal(str(comanda.total_amount)) + Decimal(str(real_price))))

        db.commit()
        return self._attach_recurrence_info(db, self.repo.get_with_relations(db, appointment.id))

    def remove_unpaid_service(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        service_id: int,
        pet_id: int | None = None,
        user_id: int | None = None,
    ):
        """
        Removes an unpaid extra service from an appointment.
        For completed appointments, marks as 'removed' (unbilled) and preserves history/clinical record.
        For non-completed appointments, removes the service from the scheduled item.
        Always records an audit log and synchronizes with any open comanda in the POS.
        """
        from datetime import datetime, timezone
        from sqlalchemy import or_, func
        from app.modules.appointments.models import AppointmentItemService, AppointmentAuditLog, AppointmentPackageCoverage
        from app.modules.sales.models import Comanda, ComandaItem, Sale, SaleItem

        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

        if appointment.is_paid:
            raise HTTPException(status_code=400, detail="Não é possível remover serviço de um agendamento já pago no caixa.")

        now = datetime.now(timezone.utc)
        found = False
        is_completed = (appointment.status == AppointmentStatus.COMPLETED)

        for item in list(appointment.items):
            if pet_id and item.pet_id != pet_id:
                continue

            # Check if covered by package
            if any(c.service_id == service_id for c in item.coverages):
                raise HTTPException(
                    status_code=400,
                    detail="Este serviço foi debitado de um pacote e não pode ser removido como avulso."
                )

            service_obj = next((s for s in item.services if s.id == service_id), None)
            if service_obj:
                service_name = service_obj.name
                service_price = getattr(service_obj, "price_cents", None)

                if is_completed:
                    # Soft removal: keep in appointment history, mark as unbilled
                    ais = db.query(AppointmentItemService).filter(
                        AppointmentItemService.appointment_item_id == item.id,
                        AppointmentItemService.service_id == service_id,
                    ).first()

                    if ais:
                        ais.status = "removed"
                        ais.removed_at = now
                        ais.removed_by_user_id = user_id
                        ais.removal_reason = "Removido manualmente no agendamento finalizado"
                        db.add(ais)
                    else:
                        ais = AppointmentItemService(
                            appointment_item_id=item.id,
                            service_id=service_id,
                            status="removed",
                            removed_at=now,
                            removed_by_user_id=user_id,
                            removal_reason="Removido manualmente no agendamento finalizado",
                        )
                        db.add(ais)

                    log = AppointmentAuditLog(
                        tenant_id=tenant_id,
                        appointment_id=appointment.id,
                        appointment_item_id=item.id,
                        service_id=service_id,
                        service_name=service_name,
                        pet_id=item.pet_id,
                        pet_name=item.pet.name if item.pet else None,
                        user_id=user_id,
                        action="service_removed",
                        notes=f"Serviço '{service_name}' marcado como Não Cobrado no agendamento finalizado",
                    )
                    db.add(log)
                else:
                    # Non-completed appointment: hard remove from scheduled item
                    item.services = [s for s in item.services if s.id != service_id]
                    if len(item.services) == 0 and len(appointment.items) > 1:
                        db.delete(item)

                    log = AppointmentAuditLog(
                        tenant_id=tenant_id,
                        appointment_id=appointment.id,
                        appointment_item_id=item.id,
                        service_id=service_id,
                        service_name=service_name,
                        pet_id=item.pet_id,
                        pet_name=item.pet.name if item.pet else None,
                        user_id=user_id,
                        action="service_removed",
                        notes=f"Serviço '{service_name}' removido do agendamento",
                    )
                    db.add(log)

                found = True

        if not found:
            raise HTTPException(status_code=404, detail="Serviço não encontrado neste agendamento.")

        # Synchronize with open comanda
        comandas = db.query(Comanda).filter(
            Comanda.tenant_id == tenant_id,
            Comanda.status == "open",
            or_(
                Comanda.appointment_id == appointment_id,
                Comanda.client_id == appointment.client_id,
            )
        ).all()

        for comanda in comandas:
            matching_items = [
                ci for ci in list(comanda.items)
                if ci.item_type == "service"
                and ci.item_id == service_id
                and (ci.appointment_id == appointment_id or comanda.appointment_id == appointment_id)
                and (not pet_id or not ci.pet_ids or pet_id in ci.pet_ids)
            ]
            for ci in matching_items:
                ci.status = "removed"
                ci.removed_at = now
                ci.removed_by_user_id = user_id
                ci.removal_reason = "Removido no agendamento"
                db.add(ci)
            db.flush()

            active_items = [ci for ci in comanda.items if getattr(ci, "status", "active") == "active"]
            remaining_subtotal = sum(ci.subtotal for ci in active_items)
            comanda.total_amount = max(0.0, float(Decimal(str(remaining_subtotal)) - Decimal(str(comanda.discount_amount))))
            if not active_items or len(active_items) == 0:
                comanda.status = "canceled"

        # Se NÃO for agendamento finalizado, verificar se deve ser cancelado automaticamente
        if not is_completed:
            total_remaining_services = sum(len(it.services) for it in appointment.items)
            if total_remaining_services == 0:
                appointment.status = AppointmentStatus.CANCELED
                appointment.notes = (appointment.notes or "") + "\n[Cancelado automaticamente: todos os serviços foram removidos]"
                db.add(appointment)
            else:
                item_ids = [item.id for item in appointment.items]
                active_coverages = (
                    db.query(AppointmentPackageCoverage)
                    .filter(AppointmentPackageCoverage.appointment_item_id.in_(item_ids))
                    .count()
                )
                active_sale_items = (
                    db.query(SaleItem)
                    .join(Sale, Sale.id == SaleItem.sale_id)
                    .filter(
                        Sale.tenant_id == tenant_id,
                        Sale.status != "canceled",
                        func.coalesce(SaleItem.status, "active") != "canceled",
                        or_(
                            SaleItem.appointment_id == appointment.id,
                            (Sale.appointment_id == appointment.id) & (SaleItem.item_type == "service"),
                        ),
                    )
                    .count()
                )
                active_comanda_items = (
                    db.query(ComandaItem)
                    .join(Comanda, Comanda.id == ComandaItem.comanda_id)
                    .filter(
                        Comanda.tenant_id == tenant_id,
                        Comanda.status == "open",
                        ComandaItem.status == "active",
                        or_(
                            ComandaItem.appointment_id == appointment.id,
                            Comanda.appointment_id == appointment.id,
                        ),
                    )
                    .count()
                )
                if active_coverages == 0 and active_sale_items == 0 and active_comanda_items == 0:
                    appointment.status = AppointmentStatus.CANCELED
                    appointment.notes = (appointment.notes or "") + "\n[Cancelado automaticamente: todos os serviços vinculados foram cancelados/removidos]"
                    db.add(appointment)

        db.commit()
        return self._attach_recurrence_info(db, self.repo.get_with_relations(db, appointment_id))

    def cancel_completed_appointment(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        reason: Optional[str] = None,
    ):
        appointment = self.repo.get_by_id(db, tenant_id, appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

        # 1. Obter relações completas
        appointment_full = self.repo.get_with_relations(db, appointment.id)
        item_ids = [item.id for item in appointment_full.items] if appointment_full.items else []

        # 2. Localizar e cancelar todas as vendas (Sales) associadas
        from app.modules.sales.models import Sale, SaleItem, Comanda, ComandaItem
        from app.modules.sales.service import SalesService
        from app.modules.commissions.models import CommissionEntry
        from app.modules.client_packages.models import ClientPackageCredit, ClientPackageUsage
        from app.modules.appointments.models import AppointmentPackageCoverage

        sales_service = SalesService()

        # Vendas diretas vinculadas ao appointment_id
        direct_sales = (
            db.query(Sale)
            .filter(
                Sale.tenant_id == tenant_id,
                Sale.appointment_id == appointment.id,
                Sale.status != "canceled",
            )
            .all()
        )

        # Vendas vinculadas via SaleItem
        item_sales = (
            db.query(Sale)
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .filter(
                Sale.tenant_id == tenant_id,
                SaleItem.appointment_id == appointment.id,
                Sale.status != "canceled",
            )
            .all()
        )

        # Vendas vinculadas via Comanda
        comanda_sales = (
            db.query(Sale)
            .join(Comanda, Comanda.id == Sale.comanda_id)
            .filter(
                Sale.tenant_id == tenant_id,
                Comanda.appointment_id == appointment.id,
                Sale.status != "canceled",
            )
            .all()
        )

        all_sales = {s.id: s for s in (direct_sales + item_sales + comanda_sales)}.values()
        canceled_sale_ids = []
        for sale in all_sales:
            try:
                # Verificar se a venda contém itens que pertencem a este agendamento (apenas serviços vinculados)
                appt_items = [
                    i for i in sale.items
                    if i.item_type == "service" and (
                        i.appointment_id == appointment.id or sale.appointment_id == appointment.id
                    )
                ]
                other_items = [
                    i for i in sale.items
                    if i not in appt_items and getattr(i, "status", "active") != "canceled"
                ]

                if other_items:
                    # VENDA MISTA: Cancela cirurgicamente APENAS os itens do agendamento, mantendo produtos e estoque intactos!
                    for item in appt_items:
                        if getattr(item, "status", "active") != "canceled":
                            sales_service.cancel_sale_item(
                                db=db,
                                tenant_id=tenant_id,
                                sale_id=sale.id,
                                item_id=item.id,
                                reason=f"Cancelamento do agendamento #{appointment.id}" + (f": {reason}" if reason else ""),
                            )
                else:
                    # VENDA EXCLUSIVA: Todos os itens eram deste agendamento, cancela a venda inteira
                    sales_service.cancel_sale(
                        db=db,
                        tenant_id=tenant_id,
                        sale_id=sale.id,
                        reason=f"Cancelamento do agendamento #{appointment.id}" + (f": {reason}" if reason else ""),
                    )
                    canceled_sale_ids.append(sale.id)
            except Exception:
                pass

        # 3. Limpar/cancelar registros de comissão relacionados ao agendamento ou às vendas canceladas
        try:
            conditions = []
            if item_ids:
                conditions.append(CommissionEntry.appointment_item_id.in_(item_ids))
            if canceled_sale_ids:
                conditions.append(CommissionEntry.sale_id.in_(canceled_sale_ids))

            if conditions:
                db.query(CommissionEntry).filter(
                    CommissionEntry.tenant_id == tenant_id,
                    or_(*conditions),
                ).delete(synchronize_session=False)
        except Exception:
            pass

        # 4. Reverter créditos de pacotes consumidos (AppointmentPackageCoverage)
        if item_ids:
            coverages = (
                db.query(AppointmentPackageCoverage)
                .filter(AppointmentPackageCoverage.appointment_item_id.in_(item_ids))
                .all()
            )

            for cov in coverages:
                if cov.client_package_credit_id:
                    credit = (
                        db.query(ClientPackageCredit)
                        .filter(ClientPackageCredit.id == cov.client_package_credit_id)
                        .first()
                    )
                    if credit:
                        credit.used_qty = max(0, credit.used_qty - 1)
                        db.add(credit)

                        client_pkg = credit.client_package
                        if client_pkg and not client_pkg.is_active:
                            client_pkg.is_active = True
                            db.add(client_pkg)

                        # Registrar log de estorno no extrato de pacotes
                        if client_pkg:
                            usage = ClientPackageUsage(
                                tenant_id=tenant_id,
                                client_package_id=client_pkg.id,
                                credit_id=credit.id,
                                change_qty=-1,
                                notes=f"Estorno por cancelamento do agendamento #{appointment.id}",
                            )
                            db.add(usage)

                db.delete(cov)

        # 5. Limpar itens de comanda aberta vinculados a este agendamento (preservando produtos e outros itens)
        comandas = (
            db.query(Comanda)
            .filter(
                Comanda.tenant_id == tenant_id,
                Comanda.status == "open",
                or_(
                    Comanda.appointment_id == appointment.id,
                    Comanda.client_id == appointment.client_id,
                ),
            )
            .all()
        )

        for comanda in comandas:
            matching_items = [
                ci
                for ci in list(comanda.items)
                if ci.appointment_id == appointment.id or (
                    ci.item_type == "service" and comanda.appointment_id == appointment.id
                )
            ]
            for ci in matching_items:
                if ci in comanda.items:
                    comanda.items.remove(ci)
                db.delete(ci)
            db.flush()

            # Se a comanda era vinculada a este agendamento, desvincula se não houver mais serviços dele
            if comanda.appointment_id == appointment.id:
                other_appt_id = next((ci.appointment_id for ci in comanda.items if ci.appointment_id), None)
                comanda.appointment_id = other_appt_id

            remaining_subtotal = sum(ci.subtotal for ci in comanda.items)
            comanda.total_amount = max(
                0.0,
                float(Decimal(str(remaining_subtotal)) - Decimal(str(comanda.discount_amount or 0))),
            )
            if not comanda.items or len(comanda.items) == 0:
                db.delete(comanda)
            else:
                db.add(comanda)

        # 6. Atualizar status do agendamento para cancelado
        appointment.status = AppointmentStatus.CANCELED
        if reason and reason.strip():
            cancel_note = f"\n[Cancelado após finalização]: {reason.strip()}"
            appointment.notes = (appointment.notes or "") + cancel_note

        db.commit()

        return self._attach_recurrence_info(db, self.repo.get_with_relations(db, appointment.id))


