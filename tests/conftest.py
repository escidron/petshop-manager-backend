import pytest
from sqlalchemy.orm import Session
from app.config.database import engine
from app.modules.tenants.models import Tenant
from app.modules.clients.models import Client
from app.modules.pets.models import Pet
from app.modules.cash_register.models import CashRegister, CashSession
from app.modules.tenant_services.models import Service
from app.modules.employees.models import Employee

# Ensure all application models and mappings are loaded
import app.main


@pytest.fixture(scope="function")
def db():
    """
    Fornece uma sessão de banco isolada para cada teste.
    Utiliza savepoint e faz rollback completo ao final do teste,
    garantindo que o banco de dados nunca seja poluído.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def tenant_id(db: Session) -> int:
    tenant = db.query(Tenant).filter(Tenant.is_active == True).first()
    if not tenant:
        raise RuntimeError("Nenhum tenant ativo encontrado no banco para testes.")
    return tenant.id


@pytest.fixture
def test_client(db: Session, tenant_id: int) -> Client:
    client = Client(
        tenant_id=tenant_id,
        name="Cliente Teste Automatizado",
        phone="(11) 99999-0000",
        is_active=True,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@pytest.fixture
def test_pet(db: Session, test_client: Client) -> Pet:
    pet = Pet(
        tenant_id=test_client.tenant_id,
        client_id=test_client.id,
        name="Pet Teste",
        species="Canino",
        breed="SRD",
        size="P",
        is_active=True,
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet


@pytest.fixture
def test_service(db: Session, tenant_id: int) -> Service:
    service = Service(
        tenant_id=tenant_id,
        name="Banho Teste",
        species=["Canino"],
        sizes=["P", "M"],
        price_cents=6000,
        is_active=True,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@pytest.fixture
def test_employee(db: Session, tenant_id: int) -> Employee:
    emp = db.query(Employee).filter(Employee.tenant_id == tenant_id, Employee.is_active == True).first()
    if not emp:
        emp = Employee(
            tenant_id=tenant_id,
            name="Funcionario Teste",
            role="Banhista",
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
    return emp


@pytest.fixture
def active_cash_session(db: Session, tenant_id: int) -> CashSession:
    """Garante que existe uma sessão de caixa aberta para permitir vendas no teste."""
    from datetime import datetime, timezone
    active = db.query(CashSession).filter(
        CashSession.tenant_id == tenant_id,
        CashSession.closed_at == None,
    ).first()
    if active:
        return active

    register = db.query(CashRegister).filter(CashRegister.tenant_id == tenant_id).first()
    if not register:
        register = CashRegister(tenant_id=tenant_id, name="Caixa Teste", is_active=True)
        db.add(register)
        db.commit()
        db.refresh(register)

    session = CashSession(
        tenant_id=tenant_id,
        cash_register_id=register.id,
        initial_amount=100.0,
        status="open",
        opened_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@pytest.fixture
def test_user(db: Session, tenant_id: int):
    from app.modules.users.models import User, TenantUser
    tu = db.query(TenantUser).filter(TenantUser.tenant_id == tenant_id, TenantUser.active == True).first()
    if tu:
        user = db.query(User).filter(User.id == tu.user_id).first()
        if user:
            return user
    user = User(
        name="User Teste",
        email=f"teste_{tenant_id}@test.com",
        password="hash",
        role="owner",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    tu = TenantUser(tenant_id=tenant_id, user_id=user.id, role="owner", active=True)
    db.add(tu)
    db.commit()
    return user

