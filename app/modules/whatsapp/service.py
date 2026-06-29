import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple

from app.config.settings import settings
from app.modules.whatsapp.models import WhatsAppMessage, WhatsAppTemplate
from app.modules.appointments.models import Appointment, AppointmentStatus, AppointmentAction
from app.modules.clients.models import Client
from app.modules.tenants.models import Tenant
from app.modules.employees.models import Employee

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.appointment_service = None

    def _get_appointment_service(self):
        # Evitar importação circular instanciando o service sob demanda
        if not self.appointment_service:
            from app.modules.appointments.service import AppointmentService
            self.appointment_service = AppointmentService()
        return self.appointment_service

    def normalize_phone_number(self, phone: str) -> str:
        if not phone:
            return ""
        return "".join(c for c in phone if c.isdigit())

    def find_client_by_phone(self, db: Session, raw_phone: str) -> list[Client]:
        digits = self.normalize_phone_number(raw_phone)
        if not digits:
            return []
        suffix = digits[-9:] if len(digits) >= 9 else digits
        return db.query(Client).filter(
            Client.phone.isnot(None),
            func.regexp_replace(Client.phone, '[^0-9]', '', 'g').like(f"%{suffix}")
        ).all()

    def get_tenant_link(self, tenant: Tenant) -> str:
        if not tenant or not tenant.phone:
            return ""
        tenant_digits = "".join(c for c in tenant.phone if c.isdigit())
        if len(tenant_digits) in (10, 11) and not tenant_digits.startswith("55"):
            tenant_digits = "55" + tenant_digits
        return f"https://wa.me/{tenant_digits}"

    def get_reschedule_link(self, db: Session, tenant_id: int, appointment: Appointment) -> str:
        """
        Tenta obter o link de agendamento online do profissional responsável pelo agendamento.
        Caso não encontre, busca o link do primeiro profissional ativo do petshop.
        """
        employee = None
        for item in appointment.items:
            if item.employee_id:
                emp = db.query(Employee).filter(Employee.id == item.employee_id).first()
                if emp and emp.schedule_token:
                    employee = emp
                    break
        
        if not employee:
            employee = db.query(Employee).filter(
                Employee.tenant_id == tenant_id,
                Employee.schedule_token.isnot(None),
                Employee.is_active == True
            ).first()

        if not employee or not employee.schedule_token:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            return self.get_tenant_link(tenant)

        # Extrai o primeiro link de origem do frontend
        import hashlib
        sig_input = f"{appointment.id}:{appointment.scheduled_at.isoformat()}:{employee.schedule_token}:{settings.JWT_SECRET_KEY}"
        signature = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()
        
        frontend_base = settings.ALLOWED_ORIGINS.split(",")[0].strip()
        return f"{frontend_base}/book/{employee.schedule_token}?appointment_id={appointment.id}&sig={signature}"

    def _render_template(self, db: Session, tenant_id: int, trigger_type: str, variables: dict) -> Tuple[str, List[dict]]:
        """
        Carrega o template ativo (específico do tenant ou padrão global) e substitui as tags.
        """
        template = db.query(WhatsAppTemplate).filter(
            WhatsAppTemplate.tenant_id == tenant_id,
            WhatsAppTemplate.trigger_type == trigger_type,
            WhatsAppTemplate.is_active == True
        ).first()

        if not template:
            # Fallback para o template global do SaaS
            template = db.query(WhatsAppTemplate).filter(
                WhatsAppTemplate.tenant_id.is_(None),
                WhatsAppTemplate.trigger_type == trigger_type,
                WhatsAppTemplate.is_active == True
            ).first()

        if not template:
            raise ValueError(f"Template ativo não encontrado para o gatilho '{trigger_type}'")

        text = template.message_template
        for k, v in variables.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))

        return text, template.buttons or []

    def send_whatsapp_notification(self, db: Session, tenant_id: int, appointment_id: int, trigger_type: str):
        """
        Carrega o template e envia a notificação transacional.
        """
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant_id
        ).first()

        if not appointment:
            logger.error(f"Agendamento {appointment_id} não encontrado para envio de WhatsApp")
            return

        client = db.query(Client).filter(Client.id == appointment.client_id).first()
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

        if not client or not client.phone:
            logger.warning(f"Cliente do agendamento {appointment_id} não possui telefone válido para WhatsApp")
            return

        # Monta dados de substituição das variáveis
        pet_names = ", ".join(item.pet.name for item in appointment.items if item.pet) or "seu pet"
        
        scheduled_dt: datetime = appointment.scheduled_at
        if scheduled_dt.tzinfo is not None:
            local_dt = scheduled_dt.astimezone(ZoneInfo("America/Sao_Paulo"))
        else:
            local_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/Sao_Paulo"))
        formatted_date = local_dt.strftime("%d/%m/%Y")
        formatted_time = local_dt.strftime("%H:%M")

        services_list = []
        employee_ids = set()
        for item in appointment.items:
            for svc in item.services:
                services_list.append(svc.name)
            if item.employee_id:
                employee_ids.add(item.employee_id)
        
        services_str = ", ".join(services_list) or "serviço"
        
        employee_names = []
        if employee_ids:
            employees = db.query(Employee).filter(Employee.id.in_(list(employee_ids))).all()
            employee_names = [emp.name for emp in employees]
        
        if employee_names:
            details_str = f"{services_str} do pet {pet_names} com {', '.join(employee_names)}"
        else:
            details_str = f"{services_str} do pet {pet_names}"

        # Escolhe o link apropriado baseado no gatilho
        if trigger_type == "appointment_canceled":
            link = self.get_reschedule_link(db, tenant_id, appointment)
        else:
            link = self.get_tenant_link(tenant)

        variables = {
            "client_name": client.name,
            "petshop_name": tenant.name,
            "pet_names": pet_names,
            "date": formatted_date,
            "time": formatted_time,
            "details": details_str,
            "link": link
        }

        try:
            content, template_buttons = self._render_template(db, tenant_id, trigger_type, variables)
            buttons = []
            if template_buttons:
                for btn in template_buttons:
                    buttons.append({
                        "id": f"{btn['id']}:{appointment_id}",
                        "text": btn["text"]
                    })
        except Exception as e:
            logger.error(f"Erro ao carregar ou renderizar template: {str(e)}")
            return

        phone = self.normalize_phone_number(client.phone)

        # Salva o log de envio
        msg = WhatsAppMessage(
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            phone_number=phone,
            direction="outbound",
            content=content,
            buttons=buttons
        )
        db.add(msg)
        db.commit()

        if settings.whatsapp_sandbox_mode:
            logger.info(f"[SANDBOX MODE] Mensagem [{trigger_type}] enviada para {phone}: {content}")
        else:
            self._send_meta_api_message(phone, content, buttons)

    def send_appointment_confirmation(self, db: Session, tenant_id: int, appointment_id: int):
        """
        Dispara a confirmação instantânea
        """
        self.send_whatsapp_notification(db, tenant_id, appointment_id, "instant_confirmation")

    def process_incoming_message(self, db: Session, from_number: str, text: str, button_payload: str = None) -> WhatsAppMessage:
        """
        Processa mensagens de entrada, lidando com botões de confirmar, cancelar e reagendar.
        """
        normalized_from = self.normalize_phone_number(from_number)
        
        # Registrar inbound no histórico
        inbound_msg = WhatsAppMessage(
            phone_number=normalized_from,
            direction="inbound",
            content=text,
            buttons=None
        )
        db.add(inbound_msg)
        db.flush()

        clients = self.find_client_by_phone(db, normalized_from)
        if not clients:
            reply_text = (
                "Olá! Não conseguimos identificar o seu cadastro em nossa central de pet shops. "
                "Por favor, entre em contato diretamente com o seu pet shop para mais informações."
            )
            return self._send_reply(db, normalized_from, reply_text)

        client_ids = [c.id for c in clients]

        # 1. Verifica se o payload do botão possui o ID do agendamento embutido (ex: "confirm:156")
        target_appointment_id = None
        if button_payload and ":" in button_payload:
            parts = button_payload.split(":", 1)
            try:
                target_appointment_id = int(parts[1])
            except ValueError:
                pass

        appointment = None
        if target_appointment_id:
            appt = db.query(Appointment).filter(
                Appointment.id == target_appointment_id,
                Appointment.client_id.in_(client_ids)
            ).first()
            if appt and appt.status in (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED):
                appointment = appt

        # 2. Tenta identificar o agendamento a partir da última mensagem de saída enviada para este número
        if not appointment:
            last_outbound = (
                db.query(WhatsAppMessage)
                .filter(
                    WhatsAppMessage.phone_number == normalized_from,
                    WhatsAppMessage.direction == "outbound",
                    WhatsAppMessage.appointment_id.isnot(None)
                )
                .order_by(WhatsAppMessage.created_at.desc())
                .first()
            )
            if last_outbound:
                appt = db.query(Appointment).filter(Appointment.id == last_outbound.appointment_id).first()
                if appt and appt.status in (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED):
                    appointment = appt

        # 3. Caso contrário (ou se o agendamento já foi cancelado/concluído), busca o pendente mais recente
        if not appointment:
            appointment = (
                db.query(Appointment)
                .filter(
                    Appointment.client_id.in_(client_ids),
                    Appointment.status == AppointmentStatus.PENDING
                )
                .order_by(Appointment.scheduled_at.desc())
                .first()
            )

        # 4. Se ainda não achar, busca o confirmado mais recente
        if not appointment:
            appointment = (
                db.query(Appointment)
                .filter(
                    Appointment.client_id.in_(client_ids),
                    Appointment.status == AppointmentStatus.CONFIRMED
                )
                .order_by(Appointment.scheduled_at.desc())
                .first()
            )

        if not appointment:
            reply_text = (
                "Olá! Não encontramos nenhum agendamento pendente ou confirmado para este número em nossa central. "
                "Para agendar ou tirar dúvidas, fale direto com o seu pet shop."
            )
            return self._send_reply(db, normalized_from, reply_text)

        inbound_msg.appointment_id = appointment.id
        inbound_msg.tenant_id = appointment.tenant_id

        tenant = db.query(Tenant).filter(Tenant.id == appointment.tenant_id).first()
        tenant_name = tenant.name if tenant else "o pet shop"
        tenant_phone = tenant.phone if tenant else ""
        tenant_link = self.get_tenant_link(tenant)

        is_confirm = False
        is_cancel = False
        is_reschedule = False

        action_payload = button_payload
        if button_payload and ":" in button_payload:
            action_payload = button_payload.split(":", 1)[0]

        if action_payload == "confirm":
            is_confirm = True
        elif action_payload == "cancel":
            is_cancel = True
        elif action_payload == "reschedule":
            is_reschedule = True
        else:
            # Parser do texto livre
            cleaned_text = text.strip().lower()
            confirm_keywords = ["1", "sim", "confirmar", "ok", "confirmar agendamento", "vou", "confirmado"]
            cancel_keywords = ["2", "não", "nao", "cancelar", "cancelar agendamento", "remover"]
            reschedule_keywords = ["3", "reagendar", "mudar", "alterar", "outro dia", "outro horario", "outro horário", "remarcar"]

            if any(k in cleaned_text for k in confirm_keywords):
                is_confirm = True
            elif any(k in cleaned_text for k in cancel_keywords):
                is_cancel = True
            elif any(k in cleaned_text for k in reschedule_keywords):
                is_reschedule = True

        app_service = self._get_appointment_service()

        if is_confirm:
            try:
                app_service.apply_action(
                    db=db,
                    tenant_id=appointment.tenant_id,
                    appointment_id=appointment.id,
                    action=AppointmentAction.CONFIRM,
                    by_whatsapp=True
                )
                reply_text = (
                    f"Perfeito! Seu agendamento no *{tenant_name}* foi *CONFIRMADO* com sucesso!\n\n"
                    f"Esperamos você no horário marcado. Caso precise de suporte, acesse: {tenant_link}"
                )
            except Exception as e:
                logger.error(f"Erro ao confirmar agendamento via WhatsApp: {str(e)}")
                reply_text = "Houve um problema ao confirmar seu agendamento no sistema. Por favor, entre em contato direto com o pet shop."
            return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id)

        elif is_cancel:
            try:
                app_service.apply_action(
                    db=db,
                    tenant_id=appointment.tenant_id,
                    appointment_id=appointment.id,
                    action=AppointmentAction.CANCEL,
                    by_whatsapp=True
                )
                reply_text = (
                    f"Entendido. Seu agendamento no *{tenant_name}* foi *CANCELADO*.\n\n"
                    f"Caso queira reagendar, entre em contato diretamente pelo link: {tenant_link}"
                )
            except Exception as e:
                logger.error(f"Erro ao cancelar agendamento via WhatsApp: {str(e)}")
                reply_text = "Houve um problema ao cancelar seu agendamento no sistema. Por favor, entre em contato direto com o pet shop."
            return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id)

        elif is_reschedule:
            # Fluxo de reagendamento: Envia o link para o cliente escolher o novo dia/horário (sem cancelar imediatamente)
            try:
                reschedule_url = self.get_reschedule_link(db, appointment.tenant_id, appointment)
                reply_text = (
                    f"Sem problemas! Para escolher um novo dia e horário no *{tenant_name}*, "
                    f"acesse o nosso link de agendamento online: {reschedule_url}"
                )
            except Exception as e:
                logger.error(f"Erro ao processar reagendamento via WhatsApp: {str(e)}")
                reply_text = "Houve um problema ao preparar a página de reagendamento. Por favor, entre em contato direto com o pet shop para remarcar."
            return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id)

        else:
            # Fallback dinâmico carregado do banco de dados
            pet_names = ", ".join(item.pet.name for item in appointment.items if item.pet) or "seu pet"
            scheduled_dt: datetime = appointment.scheduled_at
            if scheduled_dt.tzinfo is not None:
                local_dt = scheduled_dt.astimezone(ZoneInfo("America/Sao_Paulo"))
            else:
                local_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/Sao_Paulo"))
            formatted_date = local_dt.strftime("%d/%m/%Y")
            formatted_time = local_dt.strftime("%H:%M")
            
            variables = {
                "client_name": clients[0].name,
                "petshop_name": tenant_name,
                "pet_names": pet_names,
                "date": formatted_date,
                "time": formatted_time,
                "link": tenant_link
            }
            try:
                reply_text, template_buttons = self._render_template(db, appointment.tenant_id, "fallback_invalid", variables)
                buttons = []
                if template_buttons:
                    for btn in template_buttons:
                        buttons.append({
                            "id": f"{btn['id']}:{appointment.id}",
                            "text": btn["text"]
                        })
            except Exception:
                reply_text = (
                    f"Desculpe, não entendi a sua resposta.\n\n"
                    f"Para confirmar seu agendamento no *{tenant_name}*, responda com *1* ou clique em *Confirmar Agendamento*.\n"
                    f"Para reagendar, responda com *3* ou clique em *Reagendar*.\n"
                    f"Para cancelar, responda com *2* ou clique em *Cancelar Agendamento*.\n\n"
                    f"Caso precise falar conosco, acesse: {tenant_link}"
                )
                buttons = [
                    {"id": f"confirm:{appointment.id}", "text": "Confirmar Agendamento 👍"},
                    {"id": f"reschedule:{appointment.id}", "text": "Reagendar 📅"},
                    {"id": f"cancel:{appointment.id}", "text": "Cancelar Agendamento ❌"}
                ]
            
            return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id, buttons=buttons)

    def _send_reply(self, db: Session, phone: str, text: str, appointment_id: int = None, tenant_id: int = None, buttons: list = None) -> WhatsAppMessage:
        reply_msg = WhatsAppMessage(
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            phone_number=phone,
            direction="outbound",
            content=text,
            buttons=buttons
        )
        db.add(reply_msg)
        db.commit()
        
        if settings.whatsapp_sandbox_mode:
            logger.info(f"[SANDBOX MODE] Resposta automática enviada para {phone}: {text}")
        else:
            self._send_meta_api_message(phone, text, buttons)
            
        return reply_msg

    def _send_meta_api_message(self, phone: str, content: str, buttons: list = None):
        pass
