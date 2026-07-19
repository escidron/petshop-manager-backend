from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments.models import AppointmentAction, AppointmentStatus

from .repository import AppointmentRepository
from .schemas import AppointmentCreate, AppointmentUpdate
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
        return self.repo.get_with_relations(db, first_appointment.id)

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
        return appointment

    def list_by_day(
        self,
        db: Session,
        tenant_id: int,
        day: date,
    ):
        return self.repo.list_by_day(db, tenant_id, day)

    def list_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
    ):
        return self.repo.list_by_client(db, tenant_id, client_id)
    
    def list_by_tenant(
        self,
        db: Session,
        tenant_id: int,
        start_date=None,
        end_date=None,
    ):
        return self.repo.list_by_tenant(db, tenant_id, start_date=start_date, end_date=end_date)

    # ---------- UPDATE ----------
    def update(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        data: AppointmentUpdate,
    ):
        appointment = self.get(db, tenant_id, appointment_id)

        # 🔹 Atualizar campos simples
        if data.scheduled_at is not None:
            appointment.scheduled_at = data.scheduled_at

        if data.notes is not None:
            appointment.notes = data.notes

        # 🔹 Se vier items → reconstruir
        if data.items is not None:

            # Remove todos os items antigos
            self.repo.delete_items(db, appointment)

            # Recria baseado no payload
            for item in data.items:

                self._validate_pet(
                    db,
                    tenant_id,
                    appointment.client_id,
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

        db.commit()

        return self.repo.get_with_relations(db, appointment.id)
        
    def assign_employees(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        assignments: list,
    ):
        appointment = self.get(db, tenant_id, appointment_id)
        return self.repo.assign_employees(db, appointment.id, assignments)

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
    def _validate_pet(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
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

            # Coleta serviços cobertos por pacote que têm funcionário vinculado
            covered_with_employee = [
                (item, service)
                for item in appointment_full.items
                for service in item.services
                if (item.id, service.id) in covered_pairs
                and item_emp_maps[item.id].get(service.id)
            ]

            # Cria venda R$ 0 para que o relatório de comissões tenha referência de venda
            if covered_with_employee:
                from app.modules.sales.models import Sale, SaleItem  # lazy: evita importação circular
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

                for item, service in covered_with_employee:
                    employee_id = item_emp_maps[item.id][service.id]
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
                    )
                    db.add(sale_item)
                    db.flush()

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

    def list_open_invoices(self, db: Session, tenant_id: int):
        return self.repo.list_open_invoices(db, tenant_id)

    def list_highlighted_days(
        self,
        db: Session,
        tenant_id: int,
        start_date=None,
        end_date=None,
    ) -> list[date]:
        return self.repo.list_highlighted_days(db, tenant_id, start_date=start_date, end_date=end_date)

