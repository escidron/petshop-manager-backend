from sqlalchemy.orm import Session

from app.modules.plans.models import Plan
from app.modules.tenants.models import TenantType


def seed_plans(db: Session):
    plans = [
        {
            "name": "Teste Gratis",
            "code": "FREE_TRIAL",
            "price_cents": 0,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 30,
            "is_active": True,
        },
        {
            "name": "Data Pet Pro",
            "code": "MONTHLY",
            "price_cents": 14990,  # 149.90 em centavos
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        # Pacotes WhatsApp (Avulsos para período trial ou add-on)
        {
            "name": "WhatsApp - 200 Mensagens",
            "code": "pkg_200",
            "price_cents": 2490,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        {
            "name": "WhatsApp - 300 Mensagens",
            "code": "pkg_300",
            "price_cents": 3490,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        {
            "name": "WhatsApp - 500 Mensagens",
            "code": "pkg_500",
            "price_cents": 4990,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        {
            "name": "WhatsApp - 750 Mensagens",
            "code": "pkg_750",
            "price_cents": 6990,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        {
            "name": "WhatsApp - 1.000 Mensagens",
            "code": "pkg_1000",
            "price_cents": 9990,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
        {
            "name": "WhatsApp - 2.000 Mensagens",
            "code": "pkg_2000",
            "price_cents": 16990,
            "currency": "BRL",
            "billing_cycle": "monthly",
            "trial_days": 0,
            "is_active": True,
        },
    ]

    # Limpeza de segurança: remove quaisquer planos combo legados do banco
    db.query(Plan).filter(Plan.code.like("combo_%")).delete(synchronize_session=False)
    db.commit()

    for plan_data in plans:
        existing = db.query(Plan).filter(
            Plan.code == plan_data["code"]
        ).first()

        if existing:
            # Mantém planos existentes sincronizados com a definição do código
            existing.name = plan_data["name"]
            existing.price_cents = plan_data["price_cents"]
            existing.currency = plan_data["currency"]
            existing.billing_cycle = plan_data["billing_cycle"]
            existing.trial_days = plan_data["trial_days"]
            existing.is_active = plan_data["is_active"]
            existing.pagarme_plan_id = None
        else:
            plan = Plan(**plan_data)
            plan.pagarme_plan_id = None
            db.add(plan)

    db.commit()


def seed_tenant_types(db: Session):
    types = [
        {
            "code": "petshop",
            "name": "Petshop / Banho e Tosa",
            "is_active": True,
        }
    ]

    for type_data in types:
        existing = db.query(TenantType).filter(
            TenantType.code == type_data["code"]
        ).first()

        if existing:
            existing.name = type_data["name"]
            existing.is_active = type_data["is_active"]
        else:
            t_type = TenantType(**type_data)
            db.add(t_type)

    db.commit()


def sync_all_seeds(db: Session):
    """Sincroniza todos os metadados do sistema (planos, tipos de tenant, templates).
    Pode ser executado com segurança no boot da aplicação (lifespan) de qualquer ambiente.
    """
    seed_plans(db)
    seed_tenant_types(db)
    seed_whatsapp_templates(db)


def seed_whatsapp_templates(db: Session):
    from app.modules.whatsapp.models import WhatsAppTemplate

    templates = [
        {
            "trigger_type": "instant_confirmation",
            "message_template": (
                "Olá, {{client_name}}! Aqui é o assistente de agendamentos do {{petshop_name}}.\n\n"
                "Seu horário está marcado para o dia {{date}} às {{time}} ({{details}}).\n\n"
                "Por favor, confirme se poderá comparecer ou reagendar clicando em um dos botões abaixo.\n\n"
                "Caso precise falar conosco, acesse: {{link}}"
            ),
            "buttons": [
                {"id": "confirm", "text": "Confirmar Agendamento 👍"},
                {"id": "reschedule", "text": "Reagendar 📅"},
                {"id": "cancel", "text": "Cancelar Agendamento ❌"}
            ],
            "is_active": True,
        },
        {
            "trigger_type": "reminder_24h",
            "message_template": (
                "Olá, {{client_name}}! Passando para lembrar que amanhã você tem um horário agendado no {{petshop_name}} "
                "para o dia {{date}} às {{time}} ({{details}}).\n\n"
                "Você confirma o comparecimento? Use os botões abaixo para nos avisar ou solicitar o reagendamento.\n\n"
                "Caso precise falar conosco, acesse: {{link}}"
            ),
            "buttons": [
                {"id": "confirm", "text": "Confirmar 👍"},
                {"id": "reschedule", "text": "Reagendar 📅"},
                {"id": "cancel", "text": "Cancelar ❌"}
            ],
            "is_active": True,
        },
        {
            "trigger_type": "pet_ready",
            "message_template": (
                "Olá, {{client_name}}! O {{pet_names}} já terminou o serviço e está pronto para ser retirado "
                "no {{petshop_name}}! 🐾\n\n"
                "Caso precise de suporte ou queira falar conosco, acesse: {{link}}"
            ),
            "buttons": [
                {"id": "confirm_ok", "text": "Estou a caminho! 🚗"}
            ],
            "is_active": True,
        },
        {
            "trigger_type": "appointment_canceled",
            "message_template": (
                "Olá, {{client_name}}. Seu agendamento no *{{petshop_name}}* para o dia {{date}} foi cancelado.\n\n"
                "Caso queira reagendar um novo horário, acesse o nosso link de agendamento online: {{link}}"
            ),
            "buttons": [
                {"id": "reschedule", "text": "Reagendar Online 📅"}
            ],
            "is_active": True,
        },
        {
            "trigger_type": "fallback_invalid",
            "message_template": (
                "Desculpe, não entendi a sua resposta.\n\n"
                "Para confirmar seu agendamento no *{{petshop_name}}*, responda com *1* ou clique em *Confirmar Agendamento*.\n"
                "Para reagendar, responda com *3* ou clique em *Reagendar*.\n"
                "Para cancelar, responda com *2* ou clique em *Cancelar Agendamento*.\n\n"
                "Caso precise falar conosco, acesse: {{link}}"
            ),
            "buttons": [
                {"id": "confirm", "text": "Confirmar Agendamento 👍"},
                {"id": "reschedule", "text": "Reagendar 📅"},
                {"id": "cancel", "text": "Cancelar Agendamento ❌"}
            ],
            "is_active": True,
        }
    ]

    for t_data in templates:
        existing = db.query(WhatsAppTemplate).filter(
            WhatsAppTemplate.tenant_id.is_(None),
            WhatsAppTemplate.trigger_type == t_data["trigger_type"]
        ).first()

        if existing:
            existing.message_template = t_data["message_template"]
            existing.buttons = t_data["buttons"]
            existing.is_active = t_data["is_active"]
        else:
            template = WhatsAppTemplate(**t_data)
            db.add(template)

    db.commit()
