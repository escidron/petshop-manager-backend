"""
Script para popular dados de demonstração completos e realistas para um tenant específico.

Uso:
    poetry run python -m app.scripts.seed_demo_data <tenant_id>
    ou via Makefile:
    make seed-demo tenant=<tenant_id>

Cenário gerado para apresentação comercial (Demo Pitch):
    - Plano de Contas DRE padrão do sistema
    - 2 Fornecedores (Rações e Medicamentos/Cosméticos)
    - 3 Colaboradores (Banhista, Tosadora Especialista, Recepcionista)
    - Perfis de Folha de Pagamento & Benefícios para os funcionários
    - Regras de Comissionamento (10% Banhista, 15% Tosadora, 3% Balcão)
    - 15 Produtos com estoque e preço de custo (CMV)
    - 18 Serviços calibrados com duração e preços por porte/espécie
    - 2 Pacotes promocionais (Combo Banho 4x e Pacote Premium)
    - 12 Clientes completos com contatos e cidades reais
    - 18 Pets de raças populares com detalhes de porte e pelagem
    - 1 Pacote Ativo de Cliente (com 3 créditos restantes para demonstrar abatimento)
    - Caixa Principal aberto HOJE com saldo inicial e movimentações
    - 45+ Agendamentos (passados concluídos, hoje com horários livres para agendar ao vivo, e futuros)
    - Vendas automáticas vinculadas aos agendamentos e vendas de balcão
    - Comissões calculadas e registradas para os funcionários
    - Contas a Pagar e Receber (Aluguel, Energia, Fornecedores e Recebíveis de Cartão)
"""

import sys
import random
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.modules.models_loader import load_all_models
load_all_models()

from sqlalchemy import select
from app.config.database import SessionLocal

# Importação dos modelos para resolução de relacionamentos
from app.modules.tenants.models import Tenant
from app.modules.users.models import User, TenantUser
from app.modules.suppliers.models import Supplier
from app.modules.financial.repository import FinancialRepository
from app.modules.financial.models import (
    DREAccount,
    FinancialBill,
    EmployeePayrollProfile,
)
from app.modules.employees.models import Employee, EmployeeRole
from app.modules.commissions.models import (
    CommissionRule,
    CommissionEntry,
    commission_rule_employees,
)
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.products.models import Product
from app.modules.products.inventory_models import InventoryLog
from app.modules.tenant_services.models import Service
from app.modules.packages.models import Package, PackageItem
from app.modules.client_packages.models import (
    ClientPackage,
    ClientPackageCredit,
    ClientPackagePet,
)
from app.modules.cash_register.models import CashRegister, CashSession, CashMovement
from app.modules.appointments.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemService,
    AppointmentStatus,
)
from app.modules.sales.models import Sale, SaleItem, SalePayment


def seed_demo(tenant_id: int):
    db = SessionLocal()
    try:
        now = datetime.now(tz=timezone.utc)
        today = now.date()

        # 1. Valida a existência do Tenant
        tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
        if not tenant:
            print(f"\n❌ ERRO: Tenant com ID={tenant_id} não existe no banco de dados!")
            print("👉 Primeiro crie o tenant pela tela de registro/onboarding do sistema,")
            print(f"   e depois execute: make seed-demo tenant={tenant_id}\n")
            return

        print(f"🌱 Populando dados demo de ALTO NÍVEL para: {tenant.name} (tenant_id={tenant_id})...\n")

        # 2. Busca usuário associado ao tenant (para abrir caixa, auditoria, etc.)
        tenant_user = db.execute(
            select(TenantUser).where(TenantUser.tenant_id == tenant_id)
        ).scalars().first()
        user_id = tenant_user.user_id if tenant_user else None

        # ── 1. PLANO DE CONTAS DRE & TEMPLATES WHATSAPP ───────────────────────
        fin_repo = FinancialRepository()
        dre_accounts = fin_repo.seed_default_accounts_if_needed(db, tenant_id)
        print(f"  ✔ {len(dre_accounts)} contas DRE configuradas")

        from app.config.seeds import seed_whatsapp_templates
        seed_whatsapp_templates(db)
        print("  ✔ Templates globais de WhatsApp garantidos")

        # Mapeia contas DRE comuns pelo código para usar no contas a pagar
        acc_by_code = {acc.code: acc for acc in dre_accounts if acc.code}

        # ── 2. FORNECEDORES ───────────────────────────────────────────────────
        suppliers_data = [
            dict(
                name="Distribuidora Pet Brasil Ltda",
                cnpj="12.345.678/0001-90",
                phone_1="(11) 3214-5500",
                email="pedidos@petbrasil.com.br",
            ),
            dict(
                name="VetMed Distribuidora de Medicamentos & Cosméticos",
                cnpj="98.765.432/0001-10",
                phone_1="(11) 3321-8899",
                email="vendas@vetmed.com.br",
            ),
        ]
        suppliers = []
        for s in suppliers_data:
            supp = Supplier(tenant_id=tenant_id, **s)
            db.add(supp)
            suppliers.append(supp)
        db.flush()
        print(f"  ✔ {len(suppliers)} fornecedores criados")

        # ── 3. COLABORADORES & EQUIPE ─────────────────────────────────────────
        employees_data = [
            dict(
                name="João Santos",
                role=EmployeeRole.BATHER,
                phone="(11) 98111-2233",
                email="joao.banhista@petshop.com",
                admission_date=today - timedelta(days=180),
            ),
            dict(
                name="Maria Oliveira",
                role=EmployeeRole.GROOMER,
                phone="(11) 98222-3344",
                email="maria.tosadora@petshop.com",
                admission_date=today - timedelta(days=240),
            ),
            dict(
                name="Juliana Lima",
                role=EmployeeRole.RECEPTIONIST,
                phone="(11) 98333-4455",
                email="juliana.recepcao@petshop.com",
                admission_date=today - timedelta(days=120),
            ),
        ]
        employees = []
        for emp_info in employees_data:
            emp = Employee(tenant_id=tenant_id, is_active=True, **emp_info)
            db.add(emp)
            employees.append(emp)
        db.flush()

        joao_banhista = employees[0]
        maria_tosadora = employees[1]
        juliana_recepcao = employees[2]

        # Perfis de Folha de Pagamento para DRE / Relatório de RH
        payroll_profiles = [
            EmployeePayrollProfile(
                tenant_id=tenant_id,
                employee_id=joao_banhista.id,
                base_salary=1800.00,
                transport_voucher=160.00,
                meal_voucher=350.00,
                admission_date=joao_banhista.admission_date,
                is_active=True,
            ),
            EmployeePayrollProfile(
                tenant_id=tenant_id,
                employee_id=maria_tosadora.id,
                base_salary=2200.00,
                transport_voucher=160.00,
                meal_voucher=350.00,
                admission_date=maria_tosadora.admission_date,
                is_active=True,
            ),
            EmployeePayrollProfile(
                tenant_id=tenant_id,
                employee_id=juliana_recepcao.id,
                base_salary=1600.00,
                transport_voucher=160.00,
                meal_voucher=300.00,
                admission_date=juliana_recepcao.admission_date,
                is_active=True,
            ),
        ]
        for p in payroll_profiles:
            db.add(p)
        db.flush()
        print(f"  ✔ {len(employees)} funcionários com perfis de folha/DRE criados")

        # ── 4. REGRAS DE COMISSÃO ─────────────────────────────────────────────
        rule_bather = CommissionRule(
            tenant_id=tenant_id,
            name="Comissão Banhista (10% serviços)",
            applies_to="service",
            commission_type="percentage",
            value=Decimal("10.0000"),
            is_active=True,
        )
        rule_groomer = CommissionRule(
            tenant_id=tenant_id,
            name="Comissão Tosadora Especialista (15% serviços)",
            applies_to="service",
            commission_type="percentage",
            value=Decimal("15.0000"),
            is_active=True,
        )
        rule_sales = CommissionRule(
            tenant_id=tenant_id,
            name="Comissão Balcão (3% produtos)",
            applies_to="product",
            commission_type="percentage",
            value=Decimal("3.0000"),
            is_active=True,
        )
        db.add_all([rule_bather, rule_groomer, rule_sales])
        db.flush()

        # Vincula regras aos respectivos funcionários
        db.execute(commission_rule_employees.insert().values(rule_id=rule_bather.id, employee_id=joao_banhista.id))
        db.execute(commission_rule_employees.insert().values(rule_id=rule_groomer.id, employee_id=maria_tosadora.id))
        db.execute(commission_rule_employees.insert().values(rule_id=rule_sales.id, employee_id=juliana_recepcao.id))
        print("  ✔ 3 regras de comissão ativas criadas")

        # ── 5. PRODUTOS & ESTOQUE COM CMV ─────────────────────────────────────
        products_data = [
            dict(name="Ração Golden Especial Adulto 15kg",  category="Ração",      price=199.90, cost=130.00, quantity=45, min_stock=5,  sku="RAC-GLD-15"),
            dict(name="Ração Royal Canin Mini Filhote 3kg",  category="Ração",      price=94.90,  cost=60.00,  quantity=28, min_stock=3,  sku="RAC-RC-3"),
            dict(name="Ração Guabi Natural Gatos Castrados", category="Ração",      price=74.90,  cost=45.00,  quantity=20, min_stock=3,  sku="RAC-GBC-2"),
            dict(name="Shampoo Hidratante Pelos Claros 500ml", category="Higiene",  price=32.90,  cost=16.00,  quantity=35, min_stock=5,  sku="SHA-HID-500"),
            dict(name="Shampoo Antipulgas & Carrapatos 500ml", category="Higiene", price=36.90,  cost=18.00,  quantity=30, min_stock=5,  sku="SHA-APU-500"),
            dict(name="Condicionador Queratina & Argan 500ml", category="Higiene", price=34.90,  cost=17.00,  quantity=25, min_stock=4,  sku="CON-ARG-500"),
            dict(name="Coleira Antiparasitária Scalibor P",  category="Saúde",      price=89.90,  cost=52.00,  quantity=18, min_stock=3,  sku="COL-SCA-P"),
            dict(name="Coleira Antiparasitária Scalibor G",  category="Saúde",      price=99.90,  cost=58.00,  quantity=15, min_stock=3,  sku="COL-SCA-G"),
            dict(name="Vermífugo Drontal Plus Cães 10kg",    category="Saúde",      price=42.90,  cost=22.00,  quantity=22, min_stock=5,  sku="VER-DRO-1"),
            dict(name="Brinquedo Mordedor Corda Dental Pet", category="Acessórios", price=26.90,  cost=11.00,  quantity=20, min_stock=3,  sku="BRI-COR-1"),
            dict(name="Cama Nuvem Conforto Pet Tam M",       category="Acessórios", price=119.90, cost=65.00,  quantity=8,  min_stock=2,  sku="CAM-NUV-M"),
            dict(name="Pente Profissional em Aço Inox",      category="Grooming",   price=28.90,  cost=12.00,  quantity=15, min_stock=3,  sku="PEN-INO-1"),
            dict(name="Rasqueadeira Autolimpante Cabo Gel",  category="Grooming",   price=38.90,  cost=16.00,  quantity=14, min_stock=3,  sku="RAS-GEL-1"),
            dict(name="Bifinho Gourmet Carne 100g",          category="Petiscos",   price=9.90,   cost=4.00,   quantity=55, min_stock=10, sku="PET-BIF-100"),
            dict(name="Petisco Frango Desidratado Natural",  category="Petiscos",   price=19.90,  cost=9.00,   quantity=40, min_stock=10, sku="PET-FRA-80"),
        ]
        products = []
        for p in products_data:
            product = Product(tenant_id=tenant_id, is_active=True, **p)
            db.add(product)
            products.append(product)
        db.flush()

        for product in products:
            db.add(InventoryLog(
                tenant_id=tenant_id,
                product_id=product.id,
                quantity_change=product.quantity,
                change_type="manual_adjustment",
                notes="Estoque inicial - Seed comercial demo",
            ))
        print(f"  ✔ {len(products)} produtos e registros de estoque criados")

        # ── 6. SERVIÇOS ───────────────────────────────────────────────────────
        services_data = [
            # Banhos por porte
            dict(name="Banho", species="Canino", size="PP", price_cents=3800, duration_minutes=40,  description="Banho relaxante para cães micro/PP"),
            dict(name="Banho", species="Canino", size="P",  price_cents=4800, duration_minutes=45,  description="Banho completo para cães pequenos"),
            dict(name="Banho", species="Canino", size="M",  price_cents=5800, duration_minutes=55,  description="Banho completo para cães médios"),
            dict(name="Banho", species="Canino", size="G",  price_cents=7500, duration_minutes=70,  description="Banho completo para cães grandes"),
            dict(name="Banho", species="Canino", size="GG", price_cents=9500, duration_minutes=90,  description="Banho completo para cães gigantes"),
            dict(name="Banho", species="Felino",            price_cents=6500, duration_minutes=50,  description="Banho calmo e seguro para gatos"),
            # Tosa Higiênica por porte
            dict(name="Tosa Higiênica", species="Canino", size="PP", price_cents=3000, duration_minutes=30, description="Higiene de patas, barriga e região íntima PP"),
            dict(name="Tosa Higiênica", species="Canino", size="P",  price_cents=3500, duration_minutes=30, description="Higiene de patas, barriga e região íntima P"),
            dict(name="Tosa Higiênica", species="Canino", size="M",  price_cents=4500, duration_minutes=40, description="Higiene de patas, barriga e região íntima M"),
            dict(name="Tosa Higiênica", species="Canino", size="G",  price_cents=5500, duration_minutes=45, description="Higiene de patas, barriga e região íntima G"),
            # Banho & Tosa completa
            dict(name="Banho & Tosa", species="Canino", size="P",  price_cents=8500,  duration_minutes=80,  description="Banho completo + Tosa geral na máquina/tesoura"),
            dict(name="Banho & Tosa", species="Canino", size="M",  price_cents=10500, duration_minutes=95,  description="Banho completo + Tosa padrão da raça M"),
            dict(name="Banho & Tosa", species="Canino", size="G",  price_cents=14500, duration_minutes=120, description="Banho completo + Tosa padrão da raça G"),
            dict(name="Banho & Tosa", species="Canino", size="GG", price_cents=18500, duration_minutes=140, description="Banho completo + Tosa cães gigantes"),
            # Serviços adicionais
            dict(name="Hidratação Ozonizada", coat_type="long", price_cents=4500, duration_minutes=25, description="Revitalização intensa da pelagem"),
            dict(name="Desembolo & Escovação",                  price_cents=3500, duration_minutes=30, description="Remoção cuidadosa de nós"),
            dict(name="Corte & Lixamento de Unhas",             price_cents=1500, duration_minutes=15, description="Corte seguro com lixa anatômica"),
            dict(name="Limpeza Profunda de Ouvidos",            price_cents=2000, duration_minutes=15, description="Higienização com loção antisséptica"),
        ]
        services = []
        for s in services_data:
            svc = Service(tenant_id=tenant_id, is_active=True, **s)
            db.add(svc)
            services.append(svc)
        db.flush()
        print(f"  ✔ {len(services)} serviços de estética animal criados")

        # ── 7. PACOTES PROMOCIONAIS ───────────────────────────────────────────
        banho_p = next(s for s in services if s.name == "Banho" and s.size == "P")
        banho_m = next(s for s in services if s.name == "Banho" and s.size == "M")
        bt_m = next(s for s in services if s.name == "Banho & Tosa" and s.size == "M")

        pkg1 = Package(
            tenant_id=tenant_id,
            name="Pacote Mensal Banho (4x)",
            price_cents=15500,
            is_active=True,
            description="4 banhos mensais com 20% de economia",
        )
        db.add(pkg1)
        db.flush()
        db.add(PackageItem(package_id=pkg1.id, service_id=banho_p.id, quantity=4))

        pkg2 = Package(
            tenant_id=tenant_id,
            name="Pacote Spa VIP Mensal",
            price_cents=38000,
            is_active=True,
            description="2 Banhos & Tosa completas + 2 banhos de manutenção com hidratação",
        )
        db.add(pkg2)
        db.flush()
        db.add(PackageItem(package_id=pkg2.id, service_id=bt_m.id, quantity=2))
        db.add(PackageItem(package_id=pkg2.id, service_id=banho_m.id, quantity=2))
        print("  ✔ 2 pacotes de serviços promocionais criados")

        # ── 8. CLIENTES & TUTORES ─────────────────────────────────────────────
        clients_data = [
            dict(name="Ana Paula Ferreira",       phone="(11) 98765-4321", email="ana.paula@gmail.com",     city="São Paulo",     state="SP"),
            dict(name="Carlos Eduardo Santos",    phone="(11) 97654-3210", email="carlos.edu@hotmail.com",  city="São Paulo",     state="SP"),
            dict(name="Mariana Oliveira Costa",   phone="(11) 96543-2109", email="mariana.costa@gmail.com", city="São Paulo",     state="SP"),
            dict(name="Roberto Lima Silva",       phone="(11) 95432-1098", email="roberto.lima@uol.com.br", city="Guarulhos",     state="SP"),
            dict(name="Juliana Mendes Pereira",   phone="(11) 94321-0987", email="juliana.mendes@email.com",city="Osasco",        state="SP"),
            dict(name="Fernando Rodrigues Alves", phone="(11) 93210-9876", email="fernando.alves@terra.com",city="São Paulo",     state="SP"),
            dict(name="Patricia Gomes Martins",   phone="(11) 92109-8765", email="patricia.martins@globo.com", city="São Bernardo",state="SP"),
            dict(name="Thiago Nascimento Souza",  phone="(11) 91098-7654", email="thiago.souza@gmail.com",   city="São Paulo",     state="SP"),
            dict(name="Camila Barbosa Ribeiro",   phone="(11) 90987-6543", email="camila.ribeiro@outlook.com", city="Campinas",    state="SP"),
            dict(name="Lucas Carvalho Andrade",   phone="(11) 99876-5432", email="lucas.andrade@gmail.com",  city="São Paulo",     state="SP"),
            dict(name="Beatriz Teixeira Cruz",    phone="(11) 98765-1234", email="beatriz.cruz@yahoo.com",   city="Santos",        state="SP"),
            dict(name="Gustavo Moreira Lopes",    phone="(11) 97654-2345", email="gustavo.lopes@gmail.com",  city="São Paulo",     state="SP"),
        ]
        clients = []
        for idx, c in enumerate(clients_data):
            client = Client(
                tenant_id=tenant_id,
                is_active=True,
                created_at=now - timedelta(days=60 - (idx * 4)),
                **c,
            )
            db.add(client)
            clients.append(client)
        db.flush()
        print(f"  ✔ {len(clients)} clientes cadastrados")

        # ── 9. PETS ───────────────────────────────────────────────────────────
        pets_raw = [
            dict(client_idx=0,  name="Thor",     species="Canino", breed="Golden Retriever", size="G",  coat_type="long",   gender="male",   age=3, age_unit="years"),
            dict(client_idx=0,  name="Mel",      species="Felino", breed="Persa",            size="P",  coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=1,  name="Bolt",     species="Canino", breed="Bulldog Francês",  size="P",  coat_type="short",  gender="male",   age=4, age_unit="years"),
            dict(client_idx=1,  name="Nina",     species="Canino", breed="Shih Tzu",         size="PP", coat_type="long",   gender="female", age=5, age_unit="years"),
            dict(client_idx=2,  name="Luna",     species="Canino", breed="Poodle",           size="P",  coat_type="curly",  gender="female", age=2, age_unit="years"),
            dict(client_idx=3,  name="Rex",      species="Canino", breed="Pastor Alemão",    size="G",  coat_type="double", gender="male",   age=6, age_unit="years"),
            dict(client_idx=3,  name="Pipoca",   species="Felino", breed="SRD (Vira-lata)",   size="P",  coat_type="short",  gender="female", age=3, age_unit="years"),
            dict(client_idx=4,  name="Lola",     species="Canino", breed="Yorkshire Terrier",size="PP", coat_type="long",   gender="female", age=3, age_unit="years"),
            dict(client_idx=5,  name="Max",      species="Canino", breed="Labrador",         size="G",  coat_type="short",  gender="male",   age=5, age_unit="years"),
            dict(client_idx=5,  name="Coco",     species="Canino", breed="Maltês",           size="PP", coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=6,  name="Simba",    species="Felino", breed="Maine Coon",       size="M",  coat_type="long",   gender="male",   age=4, age_unit="years"),
            dict(client_idx=7,  name="Goku",     species="Canino", breed="Akita",            size="G",  coat_type="double", gender="male",   age=3, age_unit="years"),
            dict(client_idx=8,  name="Fofinha",  species="Canino", breed="Bichon Frisé",     size="P",  coat_type="curly",  gender="female", age=1, age_unit="years"),
            dict(client_idx=8,  name="Bigode",   species="Felino", breed="Ragdoll",          size="M",  coat_type="long",   gender="male",   age=5, age_unit="years"),
            dict(client_idx=9,  name="Duke",     species="Canino", breed="Rottweiler",       size="GG", coat_type="short",  gender="male",   age=4, age_unit="years"),
            dict(client_idx=10, name="Princesa", species="Canino", breed="Spitz Alemão",     size="PP", coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=10, name="Mia",      species="Felino", breed="Siamês",           size="P",  coat_type="short",  gender="female", age=3, age_unit="years"),
            dict(client_idx=11, name="Bruno",    species="Canino", breed="Beagle",           size="M",  coat_type="short",  gender="male",   age=5, age_unit="years"),
        ]
        pets = []
        for raw in pets_raw:
            c_idx = raw.pop("client_idx")
            pet = Pet(tenant_id=tenant_id, client_id=clients[c_idx].id, is_active=True, **raw)
            db.add(pet)
            pets.append(pet)
        db.flush()
        print(f"  ✔ {len(pets)} pets vinculados com sucesso")

        # ── 10. PACOTE ATIVO DE CLIENTE (DEMONSTRAÇÃO DE CRÉDITOS) ───────────
        client_pkg = ClientPackage(
            tenant_id=tenant_id,
            client_id=clients[0].id,
            package_id=pkg1.id,
            package_name=pkg1.name,
            is_active=True,
            is_paid=True,
            created_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=20),
        )
        db.add(client_pkg)
        db.flush()

        # Vincula o pacote ao pet Thor
        db.execute(ClientPackagePet.__table__.insert().values(client_package_id=client_pkg.id, pet_id=pets[0].id))

        # Adiciona 4 créditos com 1 já utilizado
        db.add(ClientPackageCredit(
            client_package_id=client_pkg.id,
            service_id=banho_p.id,
            service_name=banho_p.name,
            total_qty=4,
            used_qty=1,
        ))
        print("  ✔ 1 pacote com créditos ativos criado para demonstrar abatimento na tela do cliente")

        # ── 11. FRENTE DE CAIXA (ABERTO HOJE PARA APRESENTAÇÃO) ───────────────
        cash_register = CashRegister(
            tenant_id=tenant_id,
            name="Caixa Balcão Principal",
            is_active=True,
        )
        db.add(cash_register)
        db.flush()

        # Sessão de caixa aberta hoje pela manhã
        opened_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        cash_session = CashSession(
            tenant_id=tenant_id,
            cash_register_id=cash_register.id,
            status="open",
            opened_at=opened_time,
            opened_by_user_id=user_id,
            initial_amount=150.00,
        )
        db.add(cash_session)
        db.flush()

        # Movimento inicial (fundo de troco)
        current_cash_balance = Decimal("150.00")
        db.add(CashMovement(
            tenant_id=tenant_id,
            session_id=cash_session.id,
            user_id=user_id,
            type="opening",
            amount=150.00,
            balance_after=float(current_cash_balance),
            description="Abertura de caixa - Fundo de troco inicial",
            created_at=opened_time,
        ))
        print("  ✔ Caixa aberto hoje às 08:00 com R$ 150,00 de fundo de troco")

        # ── 12. AGENDAMENTOS & AGENDA EM TEMPO REAL ───────────────────────────
        def find_service(svc_name: str, pet: Pet) -> Service:
            for s in services:
                if s.name == svc_name and (s.species is None or s.species == pet.species) and (s.size is None or s.size == pet.size):
                    return s
            for s in services:
                if s.name == svc_name and (s.species is None or s.species == pet.species):
                    return s
            return services[0]

        # 24 Agendamentos passados para histórico e relatórios de faturamento
        past_slots = [
            (-40, 9,  "completed"), (-38, 10, "completed"), (-35, 14, "completed"),
            (-32, 9,  "completed"), (-30, 11, "completed"), (-28, 10, "completed"),
            (-25, 14, "completed"), (-22, 9,  "completed"), (-20, 11, "completed"),
            (-18, 10, "completed"), (-15, 14, "completed"), (-14, 9,  "completed"),
            (-12, 11, "completed"), (-10, 10, "completed"), (-9,  14, "completed"),
            (-7,  9,  "completed"), (-6,  11, "canceled"),  (-5,  10, "completed"),
            (-4,  14, "completed"), (-3,  9,  "no_show"),   (-2,  11, "completed"),
            (-1,  10, "completed"), (-1,  14, "completed"), (-1,  16, "completed"),
        ]

        # Agendamentos de HOJE: deixa intervalos livres (10h, 13h, 15h, 17h) para simular agendamento ao vivo!
        today_slots = [
            (0,  8,  30, "completed",   "Dinheiro no balcão"),
            (0,  9,  0,  "completed",   "Pix no balcão"),
            (0,  11, 0,  "in_progress", None),
            (0,  14, 0,  "confirmed",   None),
            (0,  16, 0,  "confirmed",   None),
        ]

        # Agendamentos futuros para os próximos 15 dias
        future_slots = [
            (1,  9,  0,  "confirmed"), (1,  14, 0,  "pending"),
            (2,  10, 0,  "confirmed"), (3,  11, 0,  "confirmed"),
            (4,  14, 0,  "pending"),   (5,  9,  0,  "confirmed"),
            (7,  10, 0,  "confirmed"), (8,  14, 0,  "pending"),
            (10, 9,  0,  "confirmed"), (12, 11, 0,  "confirmed"),
            (14, 15, 0,  "pending"),
        ]

        service_combos = [
            ["Banho"],
            ["Banho & Tosa"],
            ["Tosa Higiênica"],
            ["Banho", "Corte & Lixamento de Unhas"],
            ["Banho & Tosa", "Limpeza Profunda de Ouvidos"],
            ["Banho", "Hidratação Ozonizada"],
        ]

        payment_methods = ["pix", "credit_card", "debit_card", "money"]
        appointments_created = 0
        sales_created = 0

        # Processa passados
        for i, (day_offset, hour, status) in enumerate(past_slots):
            pet = pets[i % len(pets)]
            scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)

            appt = Appointment(
                tenant_id=tenant_id,
                client_id=pet.client_id,
                scheduled_at=scheduled,
                status=AppointmentStatus(status),
            )
            db.add(appt)
            db.flush()

            combo = service_combos[i % len(service_combos)]
            item_svcs = [find_service(name, pet) for name in combo]

            appt_item = AppointmentItem(appointment_id=appt.id, pet_id=pet.id)
            db.add(appt_item)
            db.flush()

            # Atribui profissional
            for svc in item_svcs:
                assigned_emp = maria_tosadora if "Tosa" in svc.name else joao_banhista
                db.add(AppointmentItemService(
                    appointment_item_id=appt_item.id,
                    service_id=svc.id,
                    employee_id=assigned_emp.id,
                    status="active",
                ))

            appointments_created += 1

            if status == "completed":
                total = Decimal(sum(s.price_cents for s in item_svcs)) / 100
                p_method = random.choice(payment_methods)
                sale = Sale(
                    tenant_id=tenant_id,
                    client_id=pet.client_id,
                    pet_id=pet.id,
                    appointment_id=appt.id,
                    total_amount=float(total),
                    payment_method=p_method,
                    status="completed",
                    created_at=scheduled,
                )
                db.add(sale)
                db.flush()

                db.add(SalePayment(
                    sale_id=sale.id,
                    payment_method=p_method,
                    amount=float(total),
                    created_at=scheduled,
                ))

                for svc in item_svcs:
                    unit = Decimal(svc.price_cents) / 100
                    s_item = SaleItem(
                        sale_id=sale.id,
                        item_type="service",
                        item_id=svc.id,
                        name=svc.name,
                        quantity=1,
                        unit_price=float(unit),
                        subtotal=float(unit),
                    )
                    db.add(s_item)
                    db.flush()

                    # Gera comissão
                    assigned_emp = maria_tosadora if "Tosa" in svc.name else joao_banhista
                    rule = rule_groomer if assigned_emp == maria_tosadora else rule_bather
                    comm_val = (unit * (rule.value / Decimal("100"))).quantize(Decimal("0.01"))
                    db.add(CommissionEntry(
                        tenant_id=tenant_id,
                        sale_id=sale.id,
                        sale_item_id=s_item.id,
                        appointment_item_id=appt_item.id,
                        employee_id=assigned_emp.id,
                        rule_id=rule.id,
                        commission_type=rule.commission_type,
                        rate=rule.value,
                        base_amount=unit,
                        commission_amount=comm_val,
                        status="paid",
                        created_at=scheduled,
                    ))

                sales_created += 1

        # Processa agendamentos de HOJE
        for i, (day_offset, hour, minute, status, pay_info) in enumerate(today_slots):
            pet = pets[(i + 4) % len(pets)]
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            appt = Appointment(
                tenant_id=tenant_id,
                client_id=pet.client_id,
                scheduled_at=scheduled,
                status=AppointmentStatus(status),
            )
            db.add(appt)
            db.flush()

            combo = service_combos[i % len(service_combos)]
            item_svcs = [find_service(name, pet) for name in combo]

            appt_item = AppointmentItem(appointment_id=appt.id, pet_id=pet.id)
            db.add(appt_item)
            db.flush()

            for svc in item_svcs:
                assigned_emp = maria_tosadora if "Tosa" in svc.name else joao_banhista
                db.add(AppointmentItemService(
                    appointment_item_id=appt_item.id,
                    service_id=svc.id,
                    employee_id=assigned_emp.id,
                    status="active",
                ))

            appointments_created += 1

            if status == "completed":
                total = Decimal(sum(s.price_cents for s in item_svcs)) / 100
                p_method = "money" if pay_info and "Dinheiro" in pay_info else "pix"

                sale = Sale(
                    tenant_id=tenant_id,
                    client_id=pet.client_id,
                    pet_id=pet.id,
                    appointment_id=appt.id,
                    cash_session_id=cash_session.id,
                    total_amount=float(total),
                    payment_method=p_method,
                    status="completed",
                    created_at=scheduled,
                )
                db.add(sale)
                db.flush()

                db.add(SalePayment(
                    sale_id=sale.id,
                    payment_method=p_method,
                    amount=float(total),
                    created_at=scheduled,
                ))

                if p_method == "money":
                    current_cash_balance += total
                    db.add(CashMovement(
                        tenant_id=tenant_id,
                        session_id=cash_session.id,
                        user_id=user_id,
                        sale_id=sale.id,
                        type="sale",
                        amount=float(total),
                        balance_after=float(current_cash_balance),
                        description=f"Recebimento em dinheiro - Atendimento #{appt.id} ({pet.name})",
                        created_at=scheduled,
                    ))

                for svc in item_svcs:
                    unit = Decimal(svc.price_cents) / 100
                    s_item = SaleItem(
                        sale_id=sale.id,
                        item_type="service",
                        item_id=svc.id,
                        name=svc.name,
                        quantity=1,
                        unit_price=float(unit),
                        subtotal=float(unit),
                    )
                    db.add(s_item)
                    db.flush()

                    assigned_emp = maria_tosadora if "Tosa" in svc.name else joao_banhista
                    rule = rule_groomer if assigned_emp == maria_tosadora else rule_bather
                    comm_val = (unit * (rule.value / Decimal("100"))).quantize(Decimal("0.01"))
                    db.add(CommissionEntry(
                        tenant_id=tenant_id,
                        sale_id=sale.id,
                        sale_item_id=s_item.id,
                        appointment_item_id=appt_item.id,
                        employee_id=assigned_emp.id,
                        rule_id=rule.id,
                        commission_type=rule.commission_type,
                        rate=rule.value,
                        base_amount=unit,
                        commission_amount=comm_val,
                        status="pending",
                        created_at=scheduled,
                    ))

                sales_created += 1

        # Processa futuros
        for i, (day_offset, hour, minute, status) in enumerate(future_slots):
            pet = pets[(i + 8) % len(pets)]
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=day_offset)

            appt = Appointment(
                tenant_id=tenant_id,
                client_id=pet.client_id,
                scheduled_at=scheduled,
                status=AppointmentStatus(status),
            )
            db.add(appt)
            db.flush()

            combo = service_combos[(i + 2) % len(service_combos)]
            item_svcs = [find_service(name, pet) for name in combo]

            appt_item = AppointmentItem(appointment_id=appt.id, pet_id=pet.id)
            db.add(appt_item)
            db.flush()

            for svc in item_svcs:
                assigned_emp = maria_tosadora if "Tosa" in svc.name else joao_banhista
                db.add(AppointmentItemService(
                    appointment_item_id=appt_item.id,
                    service_id=svc.id,
                    employee_id=assigned_emp.id,
                    status="active",
                ))

            appointments_created += 1

        print(f"  ✔ {appointments_created} agendamentos criados com horários livres mantidos para apresentação")
        print(f"  ✔ {sales_created} vendas de serviços e comissões integradas")

        # ── 13. VENDAS AVULSAS DE PRODUTOS NO BALCÃO ──────────────────────────
        product_sales = [
            (clients[0], [products[0], products[3]], 15, "credit_card"),
            (clients[1], [products[9]], 8, "pix"),
            (clients[2], [products[1], products[13]], 20, "credit_card"),
            (clients[4], [products[4], products[11]], 12, "debit_card"),
            (clients[7], [products[2], products[14]], 25, "pix"),
            (clients[9], [products[6]], 5, "credit_card"),
            (clients[11], [products[12], products[8]], 2, "pix"),
        ]
        for client, prods, days_ago, p_method in product_sales:
            total = Decimal(sum(p.price for p in prods)) / 100
            s_date = now - timedelta(days=days_ago)

            sale = Sale(
                tenant_id=tenant_id,
                client_id=client.id,
                total_amount=float(total),
                payment_method=p_method,
                status="completed",
                created_at=s_date,
            )
            db.add(sale)
            db.flush()

            db.add(SalePayment(
                sale_id=sale.id,
                payment_method=p_method,
                amount=float(total),
                created_at=s_date,
            ))

            for prod in prods:
                unit = Decimal(prod.price) / 100
                s_item = SaleItem(
                    sale_id=sale.id,
                    item_type="product",
                    item_id=prod.id,
                    name=prod.name,
                    quantity=1,
                    unit_price=float(unit),
                    subtotal=float(unit),
                )
                db.add(s_item)
                db.flush()

                # Comissão da vendedora de balcão (Juliana)
                comm_val = (unit * (rule_sales.value / Decimal("100"))).quantize(Decimal("0.01"))
                db.add(CommissionEntry(
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    sale_item_id=s_item.id,
                    employee_id=juliana_recepcao.id,
                    rule_id=rule_sales.id,
                    commission_type=rule_sales.commission_type,
                    rate=rule_sales.value,
                    base_amount=unit,
                    commission_amount=comm_val,
                    status="paid",
                    created_at=s_date,
                ))

        print(f"  ✔ {len(product_sales)} vendas de produtos no balcão registradas")

        # ── 14. CONTAS A PAGAR & RECEBER (FINANCEIRO & DRE COMPLETO) ──────────
        acc_aluguel = acc_by_code.get("3.01") or dre_accounts[2]
        acc_energia = acc_by_code.get("3.02") or dre_accounts[3]
        acc_fornecedores = acc_by_code.get("2.01") or dre_accounts[1]

        bills = [
            # Aluguel do imóvel (mês passado pago, este mês a pagar)
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                description="Aluguel do Imóvel Comercial",
                category_id=acc_aluguel.id,
                amount=2500.00,
                paid_amount=2500.00,
                status="paid",
                due_date=today - timedelta(days=25),
                payment_date=today - timedelta(days=25),
                payment_method="bank_transfer",
            ),
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                description="Aluguel do Imóvel Comercial",
                category_id=acc_aluguel.id,
                amount=2500.00,
                paid_amount=0.0,
                status="pending",
                due_date=today + timedelta(days=10),
                payment_method="bank_slip",
            ),
            # Energia Elétrica
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                description="Conta de Energia Elétrica (Enel)",
                category_id=acc_energia.id,
                amount=480.00,
                paid_amount=480.00,
                status="paid",
                due_date=today - timedelta(days=20),
                payment_date=today - timedelta(days=20),
                payment_method="pix",
            ),
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                description="Conta de Energia Elétrica (Enel)",
                category_id=acc_energia.id,
                amount=510.00,
                paid_amount=0.0,
                status="pending",
                due_date=today + timedelta(days=12),
                payment_method="bank_slip",
            ),
            # Compra de Rações e Mercadorias (Fornecedor 1)
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                supplier_id=suppliers[0].id,
                description="NF-e 1042 - Compra de Rações Golden e Royal Canin",
                category_id=acc_fornecedores.id,
                amount=2850.00,
                paid_amount=2850.00,
                status="paid",
                due_date=today - timedelta(days=15),
                payment_date=today - timedelta(days=15),
                payment_method="bank_slip",
            ),
            # Reposição de Cosméticos (Fornecedor 2)
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="payable",
                supplier_id=suppliers[1].id,
                description="NF-e 8841 - Shampoos, Condicionadores e Vermífugos",
                category_id=acc_fornecedores.id,
                amount=1200.00,
                paid_amount=0.0,
                status="pending",
                due_date=today + timedelta(days=5),
                payment_method="bank_slip",
            ),
            # Conta a Receber (Recebíveis de cartão de crédito antecipado)
            FinancialBill(
                tenant_id=tenant_id,
                bill_type="receivable",
                description="Repasse Adquirente Cartão de Crédito (Stone)",
                amount=1840.00,
                paid_amount=0.0,
                status="pending",
                due_date=today + timedelta(days=3),
                payment_method="bank_transfer",
            ),
        ]
        for b in bills:
            db.add(b)
        db.flush()
        print(f"  ✔ {len(bills)} contas a pagar e receber registradas no módulo financeiro")

        db.commit()

        print(f"""
✨ TENANT DEMO PRONTO COM SUCESSO! ({tenant.name} | ID={tenant_id})
======================================================================
  👤 Clientes:            {len(clients)} cadastrados
  🐶 Pets:                {len(pets)} vinculados
  📦 Produtos com Estoque: {len(products)}
  ✂️ Serviços Estéticos:  {len(services)}
  🎟️ Pacotes Ativos:      1 cliente com pacote contratado
  👥 Equipe:              3 colaboradores (João, Maria, Juliana)
  💵 Caixa:               Aberto hoje com R$ {current_cash_balance:.2f} de saldo
  📅 Agendamentos:        {appointments_created} (hoje com horários livres para agendar ao vivo)
  💰 Vendas Concluídas:   {sales_created + len(product_sales)}
  📊 DRE & Contas:        Receitas, CMV, Comissões e Despesas integradas
======================================================================
O vendedor já pode logar no sistema e apresentar todas as telas!
""")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro ao popular dados demo: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Uso: poetry run python -m app.scripts.seed_demo_data <tenant_id>")
        print("Ex:  poetry run python -m app.scripts.seed_demo_data 1")
        sys.exit(1)

    seed_demo(int(sys.argv[1]))
