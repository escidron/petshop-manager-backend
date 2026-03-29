"""
Script para popular dados demo para um tenant específico.

Uso:
    python -m app.scripts.seed_demo_data <tenant_id>

Exemplo:
    python -m app.scripts.seed_demo_data 1

O que é criado:
    - 12 clientes com dados variados
    - 18 pets (cães e gatos de diferentes portes e pelagens)
    - 15 produtos (rações, higiene, acessórios, petiscos)
    - 18 serviços (banhos, tosas, corte de unhas etc. por porte)
    - 2 pacotes de serviços
    - 43 agendamentos (passados e futuros, vários status)
    - Vendas linkadas a todos os agendamentos concluídos + vendas avulsas
"""

import sys
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.config.database import SessionLocal

# Importa todos os modelos para que o SQLAlchemy resolva os relacionamentos
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.products.models import Product
from app.modules.products.inventory_models import InventoryLog
from app.modules.tenant_services.models import Service
from app.modules.appointments.models import (
    Appointment,
    AppointmentItem,
    appointment_item_services,
)
from app.modules.packages.models import Package, PackageItem
from app.modules.sales.models import Sale, SaleItem
from app.modules.plans.models import Plan  # noqa: F401
from app.modules.subscriptions.models import Subscription  # noqa: F401
from app.modules.users.models import User, TenantUser  # noqa: F401
from app.modules.tenants.models import Tenant  # noqa: F401
from app.modules.client_packages.models import ClientPackage, ClientPackageCredit  # noqa: F401


def seed_demo(tenant_id: int):
    db = SessionLocal()
    try:
        print(f"🌱 Populando dados demo para tenant_id={tenant_id}...\n")

        # ── PRODUTOS ──────────────────────────────────────────────────────────
        # Preços em centavos (o frontend armazena e lê como centavos via mapProductFromApi)
        products_data = [
            dict(name="Ração Golden Adulto 15kg",         category="Ração",      price=18990, cost=12000, quantity=50, min_stock=5,  sku="RAC-GLD-15"),
            dict(name="Ração Royal Canin Filhote 3kg",    category="Ração",      price=8990,  cost=5500,  quantity=30, min_stock=3,  sku="RAC-RC-3"),
            dict(name="Ração Gourmet Felino 2kg",         category="Ração",      price=6990,  cost=4000,  quantity=25, min_stock=3,  sku="RAC-GT-2"),
            dict(name="Shampoo Neutro Petshop 500ml",     category="Higiene",    price=2890,  cost=1400,  quantity=40, min_stock=5,  sku="SHA-NEU-500"),
            dict(name="Shampoo Antipulgas 500ml",         category="Higiene",    price=3490,  cost=1800,  quantity=35, min_stock=5,  sku="SHA-APU-500"),
            dict(name="Condicionador Pelagem Longa 500ml",category="Higiene",    price=3290,  cost=1600,  quantity=30, min_stock=4,  sku="CON-PEL-500"),
            dict(name="Coleira Antiparasitária P",        category="Saúde",      price=4500,  cost=2200,  quantity=20, min_stock=3,  sku="COL-ANT-P"),
            dict(name="Coleira Antiparasitária G",        category="Saúde",      price=5500,  cost=2800,  quantity=15, min_stock=3,  sku="COL-ANT-G"),
            dict(name="Vermífugo Drontal Plus",           category="Saúde",      price=3800,  cost=1800,  quantity=25, min_stock=5,  sku="VER-DRO-1"),
            dict(name="Brinquedo Corda Pet",              category="Acessórios", price=2490,  cost=1000,  quantity=15, min_stock=2,  sku="BRI-COR-1"),
            dict(name="Cama Pet M",                       category="Acessórios", price=8990,  cost=4500,  quantity=10, min_stock=2,  sku="CAM-PET-M"),
            dict(name="Pente Fino para Tosa",             category="Grooming",   price=1990,  cost=800,   quantity=20, min_stock=3,  sku="PEN-FIN-1"),
            dict(name="Escova Dupla Face",                category="Grooming",   price=2990,  cost=1200,  quantity=18, min_stock=3,  sku="ESC-DUP-1"),
            dict(name="Petisco Ossinho Natural 100g",     category="Petiscos",   price=1490,  cost=600,   quantity=60, min_stock=10, sku="PET-OSS-100"),
            dict(name="Petisco Frango Desidratado 80g",   category="Petiscos",   price=1890,  cost=800,   quantity=50, min_stock=10, sku="PET-FRA-80"),
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
                notes="Estoque inicial - dados demo",
            ))

        print(f"  ✔ {len(products)} produtos criados")

        # ── SERVIÇOS ──────────────────────────────────────────────────────────
        services_data = [
            # Banho por porte
            dict(name="Banho", species="Canino", size="PP", price_cents=3500, duration_minutes=45,  description="Banho completo para cães PP"),
            dict(name="Banho", species="Canino", size="P",  price_cents=4500, duration_minutes=50,  description="Banho completo para cães P"),
            dict(name="Banho", species="Canino", size="M",  price_cents=5500, duration_minutes=60,  description="Banho completo para cães M"),
            dict(name="Banho", species="Canino", size="G",  price_cents=7000, duration_minutes=75,  description="Banho completo para cães G"),
            dict(name="Banho", species="Canino", size="GG", price_cents=9000, duration_minutes=90,  description="Banho completo para cães GG"),
            dict(name="Banho", species="Felino",            price_cents=6000, duration_minutes=60,  description="Banho completo para gatos"),
            # Tosa higiênica por porte
            dict(name="Tosa Higiênica", species="Canino", size="PP", price_cents=3000, duration_minutes=30, description="Tosa higiênica cães PP"),
            dict(name="Tosa Higiênica", species="Canino", size="P",  price_cents=3500, duration_minutes=35, description="Tosa higiênica cães P"),
            dict(name="Tosa Higiênica", species="Canino", size="M",  price_cents=4500, duration_minutes=45, description="Tosa higiênica cães M"),
            dict(name="Tosa Higiênica", species="Canino", size="G",  price_cents=5500, duration_minutes=55, description="Tosa higiênica cães G"),
            # Banho & Tosa por porte
            dict(name="Banho & Tosa", species="Canino", size="P",  price_cents=7500,  duration_minutes=90,  description="Banho e tosa para cães P"),
            dict(name="Banho & Tosa", species="Canino", size="M",  price_cents=9500,  duration_minutes=105, description="Banho e tosa para cães M"),
            dict(name="Banho & Tosa", species="Canino", size="G",  price_cents=13000, duration_minutes=120, description="Banho e tosa para cães G"),
            dict(name="Banho & Tosa", species="Canino", size="GG", price_cents=17000, duration_minutes=150, description="Banho e tosa para cães GG"),
            # Serviços extras (sem restrição de porte/espécie)
            dict(name="Hidratação",         coat_type="long", price_cents=4000, duration_minutes=30, description="Hidratação de pelagem longa"),
            dict(name="Escovação",                            price_cents=2000, duration_minutes=20, description="Escovação completa"),
            dict(name="Corte de Unhas",                       price_cents=1500, duration_minutes=15, description="Corte e lixamento de unhas"),
            dict(name="Limpeza de Ouvidos",                   price_cents=2000, duration_minutes=15, description="Limpeza e higienização de ouvidos"),
        ]

        services = []
        for s in services_data:
            svc = Service(tenant_id=tenant_id, is_active=True, **s)
            db.add(svc)
            services.append(svc)
        db.flush()

        print(f"  ✔ {len(services)} serviços criados")

        # ── PACOTES ───────────────────────────────────────────────────────────
        banho_p  = next(s for s in services if s.name == "Banho" and s.size == "P")
        banho_m  = next(s for s in services if s.name == "Banho" and s.size == "M")
        bt_m     = next(s for s in services if s.name == "Banho & Tosa" and s.size == "M")

        pkg1 = Package(tenant_id=tenant_id, name="Pacote Mensal Banho (4x)", price_cents=14000, is_active=True,
                       description="4 banhos mensais com desconto especial")
        db.add(pkg1)
        db.flush()
        db.add(PackageItem(package_id=pkg1.id, service_id=banho_p.id, quantity=4))

        pkg2 = Package(tenant_id=tenant_id, name="Pacote Premium Mensal", price_cents=35000, is_active=True,
                       description="2 Banhos & Tosa + 4 banhos simples")
        db.add(pkg2)
        db.flush()
        db.add(PackageItem(package_id=pkg2.id, service_id=bt_m.id, quantity=2))
        db.add(PackageItem(package_id=pkg2.id, service_id=banho_m.id, quantity=4))

        print("  ✔ 2 pacotes criados")

        # ── CLIENTES ──────────────────────────────────────────────────────────
        clients_data = [
            dict(name="Ana Paula Ferreira",      phone="(11) 98765-4321", email="ana.ferreira@email.com",     city="São Paulo",     state="SP"),
            dict(name="Carlos Eduardo Santos",   phone="(11) 97654-3210", email="carlos.santos@gmail.com",    city="São Paulo",     state="SP"),
            dict(name="Mariana Oliveira Costa",  phone="(11) 96543-2109", email="mariana.costa@hotmail.com",  city="São Paulo",     state="SP"),
            dict(name="Roberto Lima Silva",      phone="(11) 95432-1098",                                     city="Guarulhos",     state="SP"),
            dict(name="Juliana Mendes Pereira",  phone="(11) 94321-0987", email="juliana.pereira@email.com",  city="Osasco",        state="SP"),
            dict(name="Fernando Rodrigues Alves",phone="(11) 93210-9876", email="fernando.alves@gmail.com",   city="São Paulo",     state="SP"),
            dict(name="Patricia Gomes Martins",  phone="(11) 92109-8765",                                     city="São Bernardo",  state="SP"),
            dict(name="Thiago Nascimento Souza", phone="(11) 91098-7654", email="thiago.souza@email.com",     city="São Paulo",     state="SP"),
            dict(name="Camila Barbosa Ribeiro",  phone="(11) 90987-6543", email="camila.ribeiro@gmail.com",   city="Campinas",      state="SP"),
            dict(name="Lucas Carvalho Andrade",  phone="(11) 99876-5432",                                     city="São Paulo",     state="SP"),
            dict(name="Beatriz Teixeira Cruz",   phone="(11) 98765-1234", email="beatriz.cruz@email.com",     city="Santos",        state="SP"),
            dict(name="Gustavo Moreira Lopes",   phone="(11) 97654-2345", email="gustavo.lopes@hotmail.com",  city="São Paulo",     state="SP"),
        ]

        clients = []
        for c in clients_data:
            client = Client(tenant_id=tenant_id, is_active=True, **c)
            db.add(client)
            clients.append(client)
        db.flush()

        print(f"  ✔ {len(clients)} clientes criados")

        # ── PETS ──────────────────────────────────────────────────────────────
        # client_idx referencia o índice em clients[]
        pets_raw = [
            dict(client_idx=0,  name="Thor",     species="Canino", breed="Golden Retriever",  size="G",  coat_type="long",   gender="male",   age=3, age_unit="years"),
            dict(client_idx=0,  name="Mel",      species="Felino", breed="Persa",             coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=1,  name="Bolt",     species="Canino", breed="Bulldog Francês",   size="P",  coat_type="short",  gender="male",   age=4, age_unit="years"),
            dict(client_idx=1,  name="Nina",     species="Canino", breed="Shih Tzu",          size="PP", coat_type="long",   gender="female", age=5, age_unit="years"),
            dict(client_idx=2,  name="Luna",     species="Canino", breed="Poodle",            size="P",  coat_type="curly",  gender="female", age=2, age_unit="years"),
            dict(client_idx=3,  name="Rex",      species="Canino", breed="Pastor Alemão",     size="G",  coat_type="double", gender="male",   age=6, age_unit="years"),
            dict(client_idx=3,  name="Pipoca",   species="Felino", breed="SRD",               coat_type="short",  gender="female", age=3, age_unit="years"),
            dict(client_idx=4,  name="Lola",     species="Canino", breed="Yorkshire",         size="PP", coat_type="long",   gender="female", age=3, age_unit="years"),
            dict(client_idx=5,  name="Max",      species="Canino", breed="Labrador",          size="G",  coat_type="short",  gender="male",   age=5, age_unit="years"),
            dict(client_idx=5,  name="Coco",     species="Canino", breed="Maltês",            size="PP", coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=6,  name="Simba",    species="Felino", breed="Maine Coon",        coat_type="long",   gender="male",   age=4, age_unit="years"),
            dict(client_idx=7,  name="Goku",     species="Canino", breed="Akita",             size="G",  coat_type="double", gender="male",   age=3, age_unit="years"),
            dict(client_idx=8,  name="Fofinha",  species="Canino", breed="Bichon Frisé",      size="P",  coat_type="curly",  gender="female", age=1, age_unit="years"),
            dict(client_idx=8,  name="Bigode",   species="Felino", breed="Ragdoll",           coat_type="long",   gender="male",   age=5, age_unit="years"),
            dict(client_idx=9,  name="Duke",     species="Canino", breed="Rottweiler",        size="GG", coat_type="short",  gender="male",   age=4, age_unit="years"),
            dict(client_idx=10, name="Princesa", species="Canino", breed="Pomerânia",         size="PP", coat_type="long",   gender="female", age=2, age_unit="years"),
            dict(client_idx=10, name="Mia",      species="Felino", breed="Siamês",            coat_type="short",  gender="female", age=3, age_unit="years"),
            dict(client_idx=11, name="Bruno",    species="Canino", breed="Beagle",            size="M",  coat_type="short",  gender="male",   age=5, age_unit="years"),
        ]

        pets = []
        for raw in pets_raw:
            idx = raw.pop("client_idx")
            pet = Pet(tenant_id=tenant_id, client_id=clients[idx].id, is_active=True, **raw)
            db.add(pet)
            pets.append(pet)
        db.flush()

        print(f"  ✔ {len(pets)} pets criados")

        # ── AGENDAMENTOS ──────────────────────────────────────────────────────
        now = datetime.now(tz=timezone.utc)

        def find_service(svc_name: str, pet: Pet) -> Service:
            """Encontra o serviço mais adequado para o pet, com fallbacks."""
            # Tenta: nome + espécie + porte
            for s in services:
                if (s.name == svc_name
                        and (s.species is None or s.species == pet.species)
                        and (s.size is None or s.size == pet.size)):
                    return s
            # Fallback: nome + espécie (ignora porte)
            for s in services:
                if s.name == svc_name and (s.species is None or s.species == pet.species):
                    return s
            # Último fallback: só nome
            for s in services:
                if s.name == svc_name:
                    return s
            return services[0]

        # (day_offset_from_today, hour, status)
        past_slots = [
            (-45, 9,  "completed"), (-44, 10, "completed"), (-43, 14, "completed"),
            (-40, 9,  "completed"), (-38, 11, "completed"), (-37, 10, "completed"),
            (-35, 14, "completed"), (-33, 9,  "completed"), (-30, 11, "completed"),
            (-28, 10, "completed"), (-27, 14, "completed"), (-25, 9,  "completed"),
            (-22, 11, "completed"), (-20, 10, "completed"), (-18, 14, "completed"),
            (-15, 9,  "completed"), (-13, 11, "canceled"),  (-12, 10, "completed"),
            (-10, 14, "completed"), (-8,  9,  "no_show"),   (-7,  11, "completed"),
            (-5,  10, "completed"), (-3,  14, "completed"), (-2,  9,  "completed"),
            (-1,  11, "completed"),
        ]

        # Agendamentos de hoje espalhados ao longo do dia
        today_slots = [
            (0,  8,  "completed"),
            (0,  9,  "completed"),
            (0,  9,  "in_progress"),
            (0,  10, "confirmed"),
            (0,  10, "confirmed"),
            (0,  11, "confirmed"),
            (0,  11, "pending"),
            (0,  13, "pending"),
            (0,  14, "pending"),
            (0,  14, "confirmed"),
            (0,  15, "pending"),
            (0,  16, "pending"),
        ]

        future_slots = [
            (1,  9,  "confirmed"), (1,  11, "pending"),   (1,  14, "confirmed"),
            (2,  10, "pending"),   (2,  14, "confirmed"),  (3,  9,  "confirmed"),
            (3,  11, "pending"),   (5,  10, "confirmed"),  (5,  14, "pending"),
            (7,  9,  "confirmed"), (7,  11, "confirmed"),  (8,  10, "pending"),
            (10, 14, "confirmed"), (12, 9,  "pending"),    (14, 11, "confirmed"),
            (15, 10, "pending"),   (20, 9,  "confirmed"),  (25, 14, "pending"),
        ]

        # Combinações de serviços por agendamento
        service_combos = [
            ["Banho"],
            ["Tosa Higiênica"],
            ["Banho & Tosa"],
            ["Banho", "Corte de Unhas"],
            ["Banho & Tosa", "Limpeza de Ouvidos"],
            ["Banho", "Limpeza de Ouvidos"],
            ["Escovação"],
            ["Corte de Unhas", "Limpeza de Ouvidos"],
        ]

        payment_methods = ["pix", "credit_card", "debit_card", "money"]
        appointments_created = 0
        sales_created = 0

        for i, (day_offset, hour, status) in enumerate(past_slots + today_slots + future_slots):
            pet = pets[i % len(pets)]
            scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)

            appt = Appointment(
                tenant_id=tenant_id,
                client_id=pet.client_id,
                scheduled_at=scheduled,
                status=status,
            )
            db.add(appt)
            db.flush()

            combo = service_combos[i % len(service_combos)]
            item_svcs = [find_service(name, pet) for name in combo]

            appt_item = AppointmentItem(appointment_id=appt.id, pet_id=pet.id)
            db.add(appt_item)
            db.flush()

            for svc in item_svcs:
                db.execute(
                    appointment_item_services.insert().values(
                        appointment_item_id=appt_item.id,
                        service_id=svc.id,
                    )
                )

            appointments_created += 1

            # Venda para agendamentos concluídos
            if status == "completed":
                total = Decimal(sum(s.price_cents for s in item_svcs)) / 100
                sale = Sale(
                    tenant_id=tenant_id,
                    client_id=pet.client_id,
                    appointment_id=appt.id,
                    total_amount=total,
                    payment_method=random.choice(payment_methods),
                    status="completed",
                )
                db.add(sale)
                db.flush()
                sale.created_at = scheduled  # data da venda = data do agendamento

                for svc in item_svcs:
                    unit = Decimal(svc.price_cents) / 100
                    db.add(SaleItem(
                        sale_id=sale.id,
                        item_type="service",
                        item_id=svc.id,
                        name=svc.name,
                        quantity=1,
                        unit_price=unit,
                        subtotal=unit,
                    ))
                sales_created += 1

        print(f"  ✔ {appointments_created} agendamentos criados")
        print(f"  ✔ {sales_created} vendas de serviço criadas")

        # Vendas avulsas de produtos
        product_sales = [
            (clients[0],  [products[0],  products[3]],  15),
            (clients[1],  [products[9]],                 8),
            (clients[2],  [products[1],  products[13]], 20),
            (clients[4],  [products[4],  products[11]], 12),
            (clients[7],  [products[2],  products[14]], 25),
            (clients[9],  [products[6]],                 5),
            (clients[11], [products[12], products[8]],   3),
        ]

        for client, prods, days_ago in product_sales:
            total = Decimal(sum(p.price for p in prods)) / 100
            sale = Sale(
                tenant_id=tenant_id,
                client_id=client.id,
                total_amount=total,
                payment_method=random.choice(payment_methods),
                status="completed",
            )
            db.add(sale)
            db.flush()
            sale.created_at = now - timedelta(days=days_ago)

            for prod in prods:
                unit = Decimal(prod.price) / 100
                db.add(SaleItem(
                    sale_id=sale.id,
                    item_type="product",
                    item_id=prod.id,
                    name=prod.name,
                    quantity=1,
                    unit_price=unit,
                    subtotal=unit,
                ))

        print(f"  ✔ {len(product_sales)} vendas avulsas de produtos criadas")

        db.commit()

        print(f"""
✅ Demo populado com sucesso para tenant_id={tenant_id}!
   Clientes:       {len(clients)}
   Pets:           {len(pets)}
   Produtos:       {len(products)}
   Serviços:       {len(services)}
   Pacotes:        2
   Agendamentos:   {appointments_created}  ({len(past_slots)} passados / {len(today_slots)} hoje / {len(future_slots)} futuros)
   Vendas:         {sales_created + len(product_sales)}
""")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro ao popular dados: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Uso: python -m app.scripts.seed_demo_data <tenant_id>")
        print("Ex:  python -m app.scripts.seed_demo_data 1")
        sys.exit(1)

    seed_demo(int(sys.argv[1]))
