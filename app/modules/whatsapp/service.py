import logging
import uuid
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple, Dict, Any

from app.config.settings import settings
from app.modules.whatsapp.models import WhatsAppMessage, WhatsAppTemplate
from app.modules.appointments.models import Appointment, AppointmentStatus, AppointmentAction
from app.modules.clients.models import Client
from app.modules.tenants.models import Tenant
from app.modules.employees.models import Employee

logger = logging.getLogger(__name__)

class MetaResponseError(Exception):
    def __init__(self, response):
        self.response = response
        super().__init__(f"Erro Meta Cloud API: {response.status_code} - {response.text}")

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
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) in (10, 11) and not digits.startswith("55"):
            digits = "55" + digits
        return digits

    def validate_whatsapp_phone(self, phone: str) -> Tuple[bool, str, str]:
        """
        Valida e normaliza o telefone para envio de WhatsApp.
        Retorna (is_valid, normalized_phone, error_reason).
        Identifica telefones fixos (8 dígitos após DDD) que não suportam WhatsApp.
        """
        if not phone:
            return False, "", "Telefone não informado"

        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]

        # Se já tem DDI 55
        if digits.startswith("55"):
            national = digits[2:]
        else:
            national = digits

        if len(national) == 10:
            # Telefone fixo (ex: 11 3234-5678) ou celular antigo
            # No Brasil, telefones fixos têm primeiro dígito após DDD em [2, 3, 4, 5]
            first_num = national[2]
            if first_num in ("2", "3", "4", "5"):
                return False, "55" + national, "Telefone fixo não suporta mensagens de WhatsApp"
            if first_num in ("6", "7", "8", "9"):
                # Antigo celular sem o nono dígito adicionado
                national = national[:2] + "9" + national[2:]
                return True, "55" + national, ""
            return False, "55" + national, "Formato de telefone inválido"
        elif len(national) == 11:
            # Celular padrão brasileiro com 9 dígitos (ex: 11 98765-4321)
            if national[2] != "9":
                return False, "55" + national, "Celular brasileiro deve iniciar com 9 após o DDD"
            return True, "55" + national, ""
        elif len(national) >= 12 and digits.startswith("55"):
            return True, digits, ""
        else:
            return False, digits, f"Telefone com quantidade inválida de dígitos ({len(digits)})"

    def debit_tenant_message_quota(self, db: Session, tenant_id: int) -> bool:
        """
        Incrementa atomicamente whatsapp_messages_used garantindo ACID e sem race conditions.
        Retorna True se debitado com sucesso, False se estourou a cota ou pacote inativo.
        """
        from app.modules.subscriptions.models import Subscription
        stmt = (
            update(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.whatsapp_package_status == "active",
                (
                    (Subscription.whatsapp_messages_limit == 0) |
                    (Subscription.whatsapp_messages_used < Subscription.whatsapp_messages_limit)
                )
            )
            .values(whatsapp_messages_used=Subscription.whatsapp_messages_used + 1)
            .execution_options(synchronize_session=False)
        )
        res = db.execute(stmt)
        return res.rowcount > 0

    def refund_tenant_message_quota(self, db: Session, tenant_id: int) -> bool:
        """
        Estorna atomicamente 1 mensagem da cota do petshop se a Meta notificar falha de entrega.
        """
        from app.modules.subscriptions.models import Subscription
        stmt = (
            update(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.whatsapp_messages_used > 0
            )
            .values(whatsapp_messages_used=Subscription.whatsapp_messages_used - 1)
            .execution_options(synchronize_session=False)
        )
        res = db.execute(stmt)
        return res.rowcount > 0

    def parse_meta_error(self, resp: Optional[Any] = None, exc: Optional[Exception] = None) -> Tuple[str, str, bool]:
        """
        Analisa a resposta de erro ou exceção da Meta API e retorna:
        (error_code, error_message, is_retriable)
        """
        if exc is not None:
            if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                return "NETWORK_TIMEOUT", f"Timeout ou falha de conexão com a Meta: {str(exc)}", True
            return "CLIENT_ERROR", str(exc), False

        if resp is not None:
            try:
                err_json = resp.json().get("error", {})
                code = str(err_json.get("code") or resp.status_code)
                msg = err_json.get("message") or resp.text
                err_data = err_json.get("error_data", {}).get("details", "")
                full_msg = f"[{code}] {msg}" + (f" - {err_data}" if err_data else "")

                # Códigos retentáveis (transitórios)
                # 429 = Rate limit
                # 500, 502, 503, 504 = Erros internos do servidor Meta
                # 130429 = Cloud API rate limit
                # 130497 = Throughput limit
                is_retriable = (
                    resp.status_code in (429, 500, 502, 503, 504) or
                    code in ("130429", "130497")
                )
                return code, full_msg, is_retriable
            except Exception:
                is_retriable = resp.status_code in (429, 500, 502, 503, 504)
                return str(resp.status_code), f"HTTP {resp.status_code}: {resp.text}", is_retriable

        return "UNKNOWN", "Erro desconhecido", False

    def check_tenant_package_status(self, db: Session, tenant_id: int) -> Tuple[bool, str, Optional[any]]:
        """
        Validação rigorosa de segurança do tenant:
        1. Tenant existe e está ativo.
        2. Tenant não desativou WhatsApp em preferências ou feature flags.
        3. Possui assinatura com whatsapp_package_status == 'active'.
        4. O ciclo vigente (whatsapp_period_end) não expirou.
        5. Não atingiu a cota de mensagens contratada (whatsapp_messages_used < whatsapp_messages_limit).
        """
        from app.modules.subscriptions.models import Subscription

        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, f"Tenant {tenant_id} não encontrado", None

        if hasattr(tenant, "is_active") and not tenant.is_active:
            return False, f"Tenant {tenant_id} está inativo", None

        if tenant.preferences and tenant.preferences.get("whatsapp_notifications_enabled") is False:
            return False, f"Tenant {tenant_id} desativou notificações de WhatsApp em preferências", None

        if tenant.feature_flags and tenant.feature_flags.get("whatsapp_enabled") is False:
            return False, f"Tenant {tenant_id} desativou WhatsApp em feature flags", None

        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        if not sub or sub.whatsapp_package_status != "active":
            status_curr = getattr(sub, "whatsapp_package_status", "sem_assinatura")
            return False, f"Tenant {tenant_id} não possui pacote de WhatsApp ativo (status: {status_curr})", sub

        # Validação do período de vigência
        if sub.whatsapp_period_end:
            now_dt = datetime.now(sub.whatsapp_period_end.tzinfo or ZoneInfo("UTC"))
            if sub.whatsapp_period_end < now_dt:
                return False, f"Pacote de WhatsApp do Tenant {tenant_id} expirou em {sub.whatsapp_period_end}", sub

        # Validação da cota de mensagens
        if sub.whatsapp_messages_limit > 0 and sub.whatsapp_messages_used >= sub.whatsapp_messages_limit:
            return False, f"Tenant {tenant_id} atingiu o limite de mensagens do pacote ({sub.whatsapp_messages_used}/{sub.whatsapp_messages_limit})", sub

        return True, "OK", sub

    def _is_sandbox_target(self, phone: str) -> bool:
        """
        Trava de Segurança de Ambiente:
        Garante que apenas o ambiente de produção ('production') possa disparar mensagens reais
        para clientes externos.
        
        Em ambientes não-produção (staging, development, test):
        1. Se whatsapp_sandbox_mode=True: sempre opera em modo simulado.
        2. Se ENVIRONMENT == 'staging':
           - Se whatsapp_sandbox_number estiver configurado: só permite envio se o destinatário
             for exatamente esse número de teste do desenvolvedor.
           - Para qualquer outro número: bloqueia o envio real e força modo Sandbox (apenas loga,
             sem chamar a Meta API nem gastar créditos).
        """
        if getattr(settings, "whatsapp_sandbox_mode", True):
            return True

        if getattr(settings, "ENVIRONMENT", "") == "staging":
            sandbox_number = getattr(settings, "whatsapp_sandbox_number", "") or ""
            normalized_sandbox = self.normalize_phone_number(sandbox_number) if sandbox_number else ""
            normalized_target = self.normalize_phone_number(phone)
            if not normalized_sandbox or normalized_target != normalized_sandbox:
                logger.info(
                    f"[STAGING SAFEGUARD] Bloqueado disparo real para {phone}. "
                    f"Em staging, disparos reais só são permitidos para o número de teste ({normalized_sandbox or 'nenhum configurado'})."
                )
                return True

        return False

    def find_client_by_phone(self, db: Session, raw_phone: str) -> list[Client]:
        digits = "".join(c for c in (raw_phone or "") if c.isdigit())
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
            # Auto-healing: tenta popular os templates globais caso o banco tenha sido resetado
            try:
                from app.config.seeds import seed_whatsapp_templates
                seed_whatsapp_templates(db)
                template = db.query(WhatsAppTemplate).filter(
                    WhatsAppTemplate.tenant_id.is_(None),
                    WhatsAppTemplate.trigger_type == trigger_type,
                    WhatsAppTemplate.is_active == True
                ).first()
            except Exception as ex:
                logger.warning(f"Falha ao auto-semear templates de WhatsApp: {ex}")

        if not template:
            raise ValueError(f"Template ativo não encontrado para o gatilho '{trigger_type}'")

        text = template.message_template
        for k, v in variables.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))

        return text, template.buttons or []

    def send_whatsapp_notification(
        self,
        db: Session,
        tenant_id: int,
        appointment_id: int,
        trigger_type: str,
        is_retry: bool = False
    ) -> Tuple[bool, str]:
        """
        Valida o tenant, pacote, deduplicação e telefone, disparando a notificação.
        Garante:
        1. Concorrência Segura: Bloqueio contra múltiplos envios simultâneos usando índice único e claim 'sending'.
        2. Deduplicação Absoluta: Nunca duplica mensagens outbound para o mesmo agendamento.
        3. Cobrança Justa: Débito atômico em whatsapp_messages_used SOMENTE se a Meta API devolver 200/201 (wamid).
        4. Resiliência a Falhas: Erros transitórios (429, 5xx, timeouts) agendam retentativa exponencial;
           erros permanentes (número fixo, inválido, template inexistente) encerram sem retentativa.
        """
        if not getattr(settings, "whatsapp_enabled", True):
            logger.info("Envio de WhatsApp desativado globalmente (WHATSAPP_ENABLED=False).")
            return False, "Envio desativado globalmente"

        can_send, reason, sub = self.check_tenant_package_status(db, tenant_id)
        if not can_send:
            logger.info(f"Envio de WhatsApp abortado para Tenant {tenant_id}: {reason}")
            return False, reason

        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant_id
        ).first()

        if not appointment:
            logger.error(f"Agendamento {appointment_id} não encontrado para envio de WhatsApp")
            return False, "Agendamento não encontrado"

        # Edge Case: Não enviar se o agendamento já foi cancelado ou concluído
        if appointment.status not in (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED):
            logger.info(f"Agendamento #{appointment_id} está com status '{appointment.status}'. Notificação abortada.")
            return False, f"Agendamento está com status {appointment.status}"

        # 1. Validação de Telefone do Cliente (Detecção de Fixo vs Celular)
        client = db.query(Client).filter(Client.id == appointment.client_id).first()
        if not client or not client.phone:
            logger.warning(f"Cliente do agendamento {appointment_id} não possui telefone")
            return False, "Telefone do cliente ausente"

        is_valid_phone, phone, phone_error = self.validate_whatsapp_phone(client.phone)
        max_retries = getattr(settings, "whatsapp_max_retries", 3)
        now_utc = datetime.now(ZoneInfo("UTC"))

        # 2. Verificação de Deduplicação / Registro Existente
        existing_msg = (
            db.query(WhatsAppMessage)
            .filter(
                WhatsAppMessage.appointment_id == appointment_id,
                WhatsAppMessage.trigger_type == trigger_type,
                WhatsAppMessage.direction == "outbound"
            )
            .first()
        )

        if existing_msg:
            # Já enviado ou entregue com sucesso
            if existing_msg.status in ("sent", "delivered", "read"):
                return False, f"Mensagem já enviada anteriormente (status: {existing_msg.status})"

            # Em processamento ativo por outra réplica/worker
            if existing_msg.status == "sending":
                msg_age = (now_utc - (existing_msg.created_at or now_utc)).total_seconds()
                if msg_age < 300:  # Menos de 5 minutos: outro worker está enviando
                    return False, "Mensagem está sendo enviada por outro processo"
                logger.warning(f"Mensagem #{existing_msg.id} estava presa em 'sending' há {msg_age:.0f}s. Assumindo reenvio.")

            # Limite de retentativas atingido
            if existing_msg.retry_count >= max_retries and not is_retry:
                return False, f"Mensagem esgotou o limite de {max_retries} tentativas"

        # Se o telefone for inválido permanente (ex: telefone fixo), registra e encerra sem cobrar
        if not is_valid_phone:
            logger.warning(f"Telefone '{client.phone}' do agendamento #{appointment_id} é inválido para WhatsApp: {phone_error}")
            if not existing_msg:
                perm_msg = WhatsAppMessage(
                    tenant_id=tenant_id,
                    appointment_id=appointment_id,
                    phone_number=phone or client.phone,
                    direction="outbound",
                    trigger_type=trigger_type,
                    content="Falha de validação: telefone fixo ou inválido",
                    status="failed",
                    error_code="INVALID_PHONE",
                    error_message=phone_error,
                    retry_count=max_retries,
                    next_retry_at=None
                )
                db.add(perm_msg)
                db.commit()
            return False, phone_error

        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

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
        for item in appointment.items:
            for svc in item.services:
                services_list.append(svc.name)
        services_str = ", ".join(services_list) or "serviço"

        link = self.get_tenant_link(tenant)
        client_first_name = client.name.strip().split()[0] if client.name else "Cliente"

        variables = {
            "client_name": client_first_name,
            "petshop_name": tenant.name,
            "pet_names": pet_names,
            "date": formatted_date,
            "time": formatted_time,
            "services_str": services_str,
            "link": link
        }

        # Renderiza template local
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
            logger.error(f"Erro ao carregar ou renderizar template local: {str(e)}")
            content = f"Lembrete do agendamento {formatted_date} às {formatted_time} para {pet_names}."
            buttons = [
                {"id": f"confirm:{appointment_id}", "text": "Confirmar"},
                {"id": f"cancel:{appointment_id}", "text": "Cancelar"}
            ]

        # 3. Claim Atômico do Registro no Banco (Proteção de Concorrência)
        if existing_msg:
            msg = existing_msg
            msg.status = "sending"
            msg.content = content
            msg.buttons = buttons
            db.commit()
        else:
            msg = WhatsAppMessage(
                tenant_id=tenant_id,
                appointment_id=appointment_id,
                phone_number=phone,
                direction="outbound",
                trigger_type=trigger_type,
                content=content,
                buttons=buttons,
                status="sending",
                retry_count=0
            )
            db.add(msg)
            try:
                db.commit()
            except IntegrityError:
                # Outra instância concorrente acabou de criar a mensagem neste mesmo milissegundo!
                db.rollback()
                logger.warning(f"[CONCURRENCY] Lembrete para agendamento #{appointment_id} já registrado por outra instância.")
                return False, "Conflito de concorrência: lembrete já registrado por outro processo"

        # 4. DISPARO REAL
        meta_msg_id = None
        send_error_code = None
        send_error_message = None
        is_success = False
        is_retriable = False

        if self._is_sandbox_target(phone):
            logger.info(f"[SANDBOX MODE] Mensagem [{trigger_type}] para {phone}: {content}")
            meta_msg_id = f"sandbox_{uuid.uuid4().hex[:16]}"
            is_success = True
        else:
            try:
                template_name = getattr(settings, "whatsapp_template_appointment", "lembrete_24h")
                meta_msg_id, _ = self._send_meta_template_message(
                    to_phone=phone,
                    template_name=template_name,
                    variables=variables,
                    appointment_id=appointment_id
                )
                is_success = True
                logger.info(f"Lembrete [{trigger_type}] enviado com sucesso via Meta API para {phone} (wamid: {meta_msg_id})")
            except MetaResponseError as me:
                send_error_code, send_error_message, is_retriable = self.parse_meta_error(resp=me.response)
                is_success = False
            except Exception as e:
                send_error_code, send_error_message, is_retriable = self.parse_meta_error(exc=e)
                is_success = False

        # 5. ATUALIZAÇÃO DO STATUS E GESTÃO DE COTA
        if is_success:
            msg.status = "sent"
            msg.meta_message_id = meta_msg_id
            msg.error_code = None
            msg.error_message = None
            msg.next_retry_at = None

            # DÉBITO DA COTA: Incremento atômico garantido somente em sucesso comprovado
            debited = self.debit_tenant_message_quota(db, tenant_id)
            if not debited:
                logger.warning(f"Mensagem enviada com sucesso mas tenant #{tenant_id} atingiu limite de cota.")

            db.commit()
            return True, f"Enviado com sucesso (wamid: {meta_msg_id})"

        else:
            new_retry_count = msg.retry_count + 1
            msg.status = "failed"
            msg.error_code = send_error_code
            msg.error_message = send_error_message[:2000] if send_error_message else "Erro desconhecido"
            msg.retry_count = new_retry_count

            # Lógica de Retry com Backoff Exponencial
            if is_retriable and new_retry_count < max_retries:
                # 5m, 15m, 45m...
                backoff_minutes = min(60, 5 * (3 ** (new_retry_count - 1)))
                msg.next_retry_at = now_utc + timedelta(minutes=backoff_minutes)
                logger.warning(
                    f"Falha temporária ao enviar lembrete #{appointment_id} ({send_error_code}). "
                    f"Tentativa {new_retry_count}/{max_retries}. Próxima retentativa em {backoff_minutes} min."
                )
            else:
                msg.next_retry_at = None
                msg.retry_count = max_retries  # Encerra retentativas para erros permanentes
                logger.error(f"Falha permanente ao enviar lembrete #{appointment_id} ({send_error_code}): {send_error_message}")

            # IMPORTANTE: Em caso de falha, NENHUMA cota do petshop é debitada!
            db.commit()
            return False, f"Falha no envio ({send_error_code}): {send_error_message}"

    def send_appointment_confirmation(self, db: Session, tenant_id: int, appointment_id: int):
        """
        Dispara a confirmação instantânea
        """
        if not getattr(settings, "whatsapp_enabled", True):
            return
        self.send_whatsapp_notification(db, tenant_id, appointment_id, "instant_confirmation")

    def process_incoming_message(self, db: Session, from_number: str, text: str, button_payload: str = None) -> WhatsAppMessage:
        """
        Processa mensagens de entrada, lidando com botões de confirmar, cancelar e reagendar.
        Por padrão, atualiza o agendamento no banco de dados silenciosamente sem enviar mensagens
        de réplica para trás, evitando custos adicionais e consumo desnecessário na Meta API.
        Caso o pet shop queira ativar respostas de texto automáticas, basta configurar WHATSAPP_AUTO_REPLY_ENABLED=True.
        """
        normalized_from = self.normalize_phone_number(from_number)
        
        # Registrar inbound no histórico
        inbound_msg = WhatsAppMessage(
            phone_number=normalized_from,
            direction="inbound",
            trigger_type="reply",
            status="received",
            content=text,
            buttons=None
        )
        db.add(inbound_msg)
        db.flush()

        clients = self.find_client_by_phone(db, normalized_from)
        if not clients:
            inbound_msg.error_message = "Cliente não identificado"
            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
                reply_text = (
                    "Olá! Não conseguimos identificar o seu cadastro em nossa central de pet shops. "
                    "Por favor, entre em contato diretamente com o seu pet shop para mais informações."
                )
                return self._send_reply(db, normalized_from, reply_text)
            return inbound_msg

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
            inbound_msg.error_message = "Agendamento não identificado"
            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
                reply_text = (
                    "Olá! Não encontramos nenhum agendamento pendente ou confirmado para este número em nossa central. "
                    "Para agendar ou tirar dúvidas, fale direto com o seu pet shop."
                )
                return self._send_reply(db, normalized_from, reply_text)
            return inbound_msg

        inbound_msg.appointment_id = appointment.id
        inbound_msg.tenant_id = appointment.tenant_id
        db.commit()

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

        action_clean = action_payload.strip().lower() if action_payload else ""
        if action_clean in ("confirm", "confirmar"):
            is_confirm = True
        elif action_clean in ("cancel", "cancelar"):
            is_cancel = True
        elif action_clean in ("reschedule", "reagendar"):
            is_reschedule = True
        elif text:
            # Parser do texto livre
            cleaned_text = text.strip().lower()
            confirm_keywords = ["1", "sim", "confirmar", "ok", "confirmar agendamento", "vou", "confirmado", "pode confirmar"]
            cancel_keywords = ["2", "não", "nao", "cancelar", "cancelar agendamento", "remover", "desmarcar"]
            reschedule_keywords = ["3", "reagendar", "mudar", "alterar", "outro dia", "outro horario", "outro horário", "remarcar"]

            if any(k in cleaned_text for k in confirm_keywords):
                is_confirm = True
            elif any(k in cleaned_text for k in cancel_keywords):
                is_cancel = True
            elif any(k in cleaned_text for k in reschedule_keywords):
                is_reschedule = True

        logger.info(
            f"[WHATSAPP] Ação detectada para Agendamento #{appointment.id}: "
            f"is_confirm={is_confirm}, is_cancel={is_cancel}, is_reschedule={is_reschedule} "
            f"(action_clean='{action_clean}', text='{text}')"
        )

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
                logger.info(f"[WHATSAPP] Agendamento #{appointment.id} confirmado com sucesso via cliente ({normalized_from}).")
            except Exception as e:
                logger.error(f"Erro ao confirmar agendamento via WhatsApp: {str(e)}")

            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
                reply_text = (
                    f"Perfeito! Seu agendamento no *{tenant_name}* foi *CONFIRMADO* com sucesso!\n\n"
                    f"Esperamos você no horário marcado. Caso precise de suporte, acesse: {tenant_link}"
                )
                return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id)
            return inbound_msg

        elif is_cancel:
            try:
                app_service.apply_action(
                    db=db,
                    tenant_id=appointment.tenant_id,
                    appointment_id=appointment.id,
                    action=AppointmentAction.CANCEL,
                    by_whatsapp=True
                )
                logger.info(f"[WHATSAPP] Agendamento #{appointment.id} cancelado com sucesso via cliente ({normalized_from}).")
            except Exception as e:
                logger.error(f"Erro ao cancelar agendamento via WhatsApp: {str(e)}")

            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
                reply_text = (
                    f"Entendido. Seu agendamento no *{tenant_name}* foi *CANCELADO*.\n\n"
                    f"Caso queira reagendar, entre em contato diretamente pelo link: {tenant_link}"
                )
                return self._send_reply(db, normalized_from, reply_text, appointment_id=appointment.id, tenant_id=appointment.tenant_id)
            return inbound_msg

        elif is_reschedule:
            logger.info(f"[WHATSAPP] Reagendamento solicitado via cliente ({normalized_from}) para agendamento #{appointment.id}.")
            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
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
            return inbound_msg

        else:
            logger.info(f"[WHATSAPP] Mensagem recebida de ({normalized_from}) para agendamento #{appointment.id}: {text}")
            db.commit()
            if getattr(settings, "whatsapp_auto_reply_enabled", False):
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
            return inbound_msg

    def _send_reply(self, db: Session, phone: str, text: str, appointment_id: int = None, tenant_id: int = None, buttons: list = None) -> WhatsAppMessage:
        meta_msg_id = None
        send_error = None
        is_success = False

        if self._is_sandbox_target(phone):
            logger.info(f"[SANDBOX MODE] Resposta automática enviada para {phone}: {text}")
            meta_msg_id = f"sandbox_{uuid.uuid4().hex[:16]}"
            is_success = True
        else:
            try:
                meta_msg_id, _ = self._send_meta_text_message(phone, text)
                is_success = True
            except Exception as e:
                send_error = str(e)
                logger.error(f"Falha ao enviar resposta de texto via Meta API para {phone}: {send_error}")
                is_success = False

        reply_msg = WhatsAppMessage(
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            phone_number=phone,
            direction="outbound",
            trigger_type="reply",
            content=text,
            buttons=buttons,
            status="sent" if is_success else "failed",
            meta_message_id=meta_msg_id,
            error_message=send_error
        )
        db.add(reply_msg)
        db.commit()
        return reply_msg

    def _send_meta_template_message(
        self,
        to_phone: str,
        template_name: str,
        variables: dict,
        appointment_id: int,
        language_code: str = "pt_BR"
    ) -> Tuple[str, dict]:
        """
        Envia mensagem de template oficial via Meta WhatsApp Cloud API.
        Retorna (meta_message_id, json_response).
        """
        if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID ou WHATSAPP_ACCESS_TOKEN não configurados no servidor.")

        url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json"
        }

        if template_name in ("hello_world", "3p_direct_integration_test_template"):
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en_US"}
                }
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code not in (200, 201):
                logger.error(f"Erro Meta Cloud API {template_name} [{resp.status_code}]: {resp.text}")
                raise MetaResponseError(resp)
            data = resp.json()
            messages = data.get("messages", [])
            wamid = messages[0].get("id") if messages else None
            return wamid, data

        # Conforme o template aprovado na Meta:
        # 1: petshop_name
        # 2: client_name
        # 3: date
        # 4: time
        # 5: pet_names
        # 6: services_str
        # 7: link
        named_parameters = [
            {"type": "text", "parameter_name": "petshop_name", "text": str(variables.get("petshop_name", ""))},
            {"type": "text", "parameter_name": "client_name", "text": str(variables.get("client_name", ""))},
            {"type": "text", "parameter_name": "date", "text": str(variables.get("date", ""))},
            {"type": "text", "parameter_name": "time", "text": str(variables.get("time", ""))},
            {"type": "text", "parameter_name": "pet_names", "text": str(variables.get("pet_names", ""))},
            {"type": "text", "parameter_name": "services_str", "text": str(variables.get("services_str", ""))},
            {"type": "text", "parameter_name": "link", "text": str(variables.get("link", ""))},
        ]

        button_components = [
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [
                    {"type": "payload", "payload": f"confirm:{appointment_id}"}
                ]
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "1",
                "parameters": [
                    {"type": "payload", "payload": f"cancel:{appointment_id}"}
                ]
            }
        ]

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": named_parameters
                    },
                    *button_components
                ]
            }
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        
        # Se a Meta reclamar de incompatibilidade de named parameters, tenta posicional
        if resp.status_code not in (200, 201):
            logger.warning(f"Tentativa com named parameters falhou: {resp.status_code} {resp.text}. Tentando formato posicional...")
            positional_parameters = [
                {"type": "text", "text": str(variables.get("petshop_name", ""))},
                {"type": "text", "text": str(variables.get("client_name", ""))},
                {"type": "text", "text": str(variables.get("date", ""))},
                {"type": "text", "text": str(variables.get("time", ""))},
                {"type": "text", "text": str(variables.get("pet_names", ""))},
                {"type": "text", "text": str(variables.get("services_str", ""))},
                {"type": "text", "text": str(variables.get("link", ""))},
            ]
            payload["template"]["components"][0]["parameters"] = positional_parameters
            resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code not in (200, 201):
            logger.error(f"Erro Meta Cloud API [{resp.status_code}]: {resp.text}")
            raise MetaResponseError(resp)

        data = resp.json()
        messages = data.get("messages", [])
        wamid = messages[0].get("id") if messages else None
        return wamid, data

    def _send_meta_text_message(self, to_phone: str, text: str) -> Tuple[str, dict]:
        """
        Envia mensagem de texto livre dentro da janela de 24h aberta pelo cliente.
        """
        import requests
        if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID ou WHATSAPP_ACCESS_TOKEN não configurados no servidor.")

        url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text
            }
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            logger.error(f"Erro Meta Cloud API texto [{resp.status_code}]: {resp.text}")
            raise RuntimeError(f"Erro Meta Cloud API: {resp.status_code} - {resp.text}")

        data = resp.json()
        messages = data.get("messages", [])
        wamid = messages[0].get("id") if messages else None
        return wamid, data
