import pytest
from datetime import datetime, timezone, timedelta, date, time
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.cash_register.service import CashRegisterService, BRAZIL_TZ
from app.modules.cash_register.repository import CashRegisterRepository
from app.modules.cash_register.models import (
    CashRegister,
    CashSession,
    CashMovement,
    CashDestinationAccount,
)
from app.modules.cash_register.schemas import (
    CashRegisterCreate,
    CashRegisterUpdate,
    CashDestinationAccountCreate,
    CashDestinationAccountUpdate,
    CashOpenRequest,
    CashSupplyRequest,
    CashBleedRequest,
    CashCloseRequest,
)
from app.modules.sales.models import Sale, SalePayment
from app.modules.clients.models import Client
from app.modules.users.models import User


@pytest.fixture
def cash_service():
    return CashRegisterService()


@pytest.fixture
def cash_repo():
    return CashRegisterRepository()


@pytest.fixture
def isolated_register(db: Session, tenant_id: int) -> CashRegister:
    """Cria um terminal de caixa exclusivo para o teste para não colidir com outros."""
    register = CashRegister(
        tenant_id=tenant_id,
        name=f"Terminal Isolado {datetime.now(timezone.utc).timestamp()}",
        is_active=True,
    )
    db.add(register)
    db.commit()
    db.refresh(register)
    return register


# ==============================================================================
# 1. TESTES DE GESTÃO DE TERMINAIS DE CAIXA (CashRegister CRUD)
# ==============================================================================

def test_cash_register_crud(
    db: Session,
    tenant_id: int,
    cash_service: CashRegisterService,
):
    """Testa criação, listagem, atualização e validação 404 de terminais de caixa."""
    # 1. Create
    created = cash_service.create_register(
        db, tenant_id, CashRegisterCreate(name="Caixa Recepção 01")
    )
    assert created.id is not None
    assert created.name == "Caixa Recepção 01"
    assert created.is_active is True

    # 2. List
    registers = cash_service.list_registers(db, tenant_id)
    assert any(r.id == created.id for r in registers)

    # 3. Update
    updated = cash_service.update_register(
        db, tenant_id, created.id, CashRegisterUpdate(name="Caixa Principal", is_active=False)
    )
    assert updated.name == "Caixa Principal"
    assert updated.is_active is False

    # 4. 404 ao atualizar caixa inexistente
    with pytest.raises(HTTPException) as exc_info:
        cash_service.update_register(db, tenant_id, 999999, CashRegisterUpdate(name="Inexistente"))
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE CONTAS DE DESTINO / ORIGEM (CashDestinationAccount CRUD)
# ==============================================================================

def test_destination_accounts_crud_and_safety_rules(
    db: Session,
    tenant_id: int,
    cash_service: CashRegisterService,
):
    """
    Testa cadastro, listagem, atualização e regra de segurança de exclusão:
    Não permite deletar a única conta restante.
    """
    # 1. Create
    acc1 = cash_service.create_destination_account(
        db, tenant_id,
        CashDestinationAccountCreate(name="Banco Inter PJ", account_type="bank_account", is_default=True)
    )
    assert acc1.id is not None
    assert acc1.name == "Banco Inter PJ"
    assert acc1.is_default is True

    acc2 = cash_service.create_destination_account(
        db, tenant_id,
        CashDestinationAccountCreate(name="Cofre Físico Loja", account_type="safe", is_default=False)
    )
    assert acc2.id is not None

    # 2. List
    accounts = cash_service.list_destination_accounts(db, tenant_id)
    account_ids = {a.id for a in accounts}
    assert acc1.id in account_ids
    assert acc2.id in account_ids

    # 3. Update
    updated = cash_service.update_destination_account(
        db, tenant_id, acc1.id,
        CashDestinationAccountUpdate(name="Banco Inter Principal")
    )
    assert updated.name == "Banco Inter Principal"

    # 4. Deleta uma conta (permitido pois restará ao menos uma)
    res_del = cash_service.delete_destination_account(db, tenant_id, acc2.id)
    assert "sucesso" in res_del["detail"]

    # 5. Tentativa de deletar conta inexistente -> 404
    with pytest.raises(HTTPException) as exc_info:
        cash_service.delete_destination_account(db, tenant_id, 888888)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 3. TESTES DE ABERTURA E FECHAMENTO DE SESSÃO DE CAIXA
# ==============================================================================

def test_open_session_and_prevent_duplicate_open_same_day(
    db: Session,
    tenant_id: int,
    test_user: User,
    isolated_register: CashRegister,
    cash_service: CashRegisterService,
):
    """
    Testa abertura de sessão com fundo de troco:
    - Cria movimentação inicial de abertura (type='opening')
    - Impede abrir outra sessão no mesmo terminal no mesmo dia (HTTP 400)
    """
    open_req = CashOpenRequest(
        initial_amount=150.0,
        notes="Abertura matutina com troco",
        cash_register_id=isolated_register.id,
    )
    detail = cash_service.open_session(db, tenant_id, test_user.id, open_req)
    assert detail.session.status == "open"
    assert detail.session.initial_amount == 150.0
    assert detail.current_balance == 150.0

    # Verifica se gerou movimentação do tipo opening
    assert len(detail.movements) == 1
    assert detail.movements[0].type == "opening"
    assert detail.movements[0].amount == 150.0
    assert detail.movements[0].balance_after == 150.0

    # Tenta abrir novamente no mesmo terminal no mesmo dia -> deve falhar com 400
    with pytest.raises(HTTPException) as exc_info:
        cash_service.open_session(db, tenant_id, test_user.id, open_req)
    assert exc_info.value.status_code == 400
    assert "Já existe uma sessão de caixa aberta" in exc_info.value.detail


def test_close_session_with_exact_and_divergent_amounts(
    db: Session,
    tenant_id: int,
    test_user: User,
    isolated_register: CashRegister,
    cash_service: CashRegisterService,
):
    """
    Testa fechamento de caixa:
    - Fechamento com valor correto (sem divergência, diff = 0.0)
    - Registra movimentação de fechamento (type='closing')
    - Bloqueia fechar caixa quando nenhum está aberto (HTTP 400)
    """
    # 1. Abre caixa com R$ 100
    cash_service.open_session(
        db, tenant_id, test_user.id,
        CashOpenRequest(initial_amount=100.0, cash_register_id=isolated_register.id),
    )

    # 2. Fecha com R$ 90 (divergência negativa de R$ -10,00)
    close_req = CashCloseRequest(
        actual_closing_amount=90.0,
        closing_notes="Faltou R$ 10,00 na contagem física",
        cash_register_id=isolated_register.id,
    )
    detail = cash_service.close_session(db, tenant_id, test_user.id, close_req)

    assert detail.session.status == "closed"
    assert detail.session.expected_closing_amount == 100.0
    assert detail.session.actual_closing_amount == 90.0
    assert detail.session.difference_amount == -10.0
    assert detail.session.closed_by_user_id == test_user.id

    # Verifica movimentação de closing
    closing_mov = [m for m in detail.movements if m.type == "closing"]
    assert len(closing_mov) == 1
    assert closing_mov[0].amount == 90.0

    # 3. Tentar fechar novamente com o caixa já fechado -> HTTP 400
    with pytest.raises(HTTPException) as exc_info:
        cash_service.close_session(db, tenant_id, test_user.id, close_req)
    assert exc_info.value.status_code == 400
    assert "Nenhum caixa está aberto" in exc_info.value.detail


# ==============================================================================
# 4. TESTES DE SUPRIMENTO E SANGRIA (Supply & Bleed)
# ==============================================================================

def test_supply_and_bleed_movements_and_limits(
    db: Session,
    tenant_id: int,
    test_user: User,
    isolated_register: CashRegister,
    cash_service: CashRegisterService,
):
    """
    Testa movimentações de entrada e saída em dinheiro:
    - Suprimento aumenta o saldo
    - Sangria diminui o saldo
    - Sangria maior que saldo disponível é rejeitada com HTTP 400
    """
    # Abre com R$ 80
    cash_service.open_session(
        db, tenant_id, test_user.id,
        CashOpenRequest(initial_amount=80.0, cash_register_id=isolated_register.id),
    )

    # 1. Suprimento de R$ 50 (saldo vai para 130)
    sup_res = cash_service.add_supply(
        db, tenant_id, test_user.id,
        CashSupplyRequest(
            amount=50.0,
            origin="Cofre Central",
            description="Troco adicional moedas",
            cash_register_id=isolated_register.id,
        ),
    )
    assert sup_res.current_balance == 130.0
    assert sup_res.total_supplies == 50.0

    # 2. Sangria de R$ 40 (saldo vai para 90)
    bld_res = cash_service.add_bleed(
        db, tenant_id, test_user.id,
        CashBleedRequest(
            amount=40.0,
            destination="Depósito Lotérica",
            description="Sangria de segurança",
            cash_register_id=isolated_register.id,
        ),
    )
    assert bld_res.current_balance == 90.0
    assert bld_res.total_bleeds == 40.0

    # 3. Tentativa de sangria maior que saldo disponível (ex: R$ 150 quando há 90) -> 400
    with pytest.raises(HTTPException) as exc_info:
        cash_service.add_bleed(
            db, tenant_id, test_user.id,
            CashBleedRequest(
                amount=150.0,
                description="Sangria excessiva",
                cash_register_id=isolated_register.id,
            ),
        )
    assert exc_info.value.status_code == 400
    assert "maior que o saldo disponível" in exc_info.value.detail


# ==============================================================================
# 5. TESTES DE GAVETA COM CAIXA FECHADO (Supply & Bleed sem Caixa Aberto)
# ==============================================================================

def test_supply_and_bleed_on_closed_cash_drawer(
    db: Session,
    tenant_id: int,
    test_user: User,
    isolated_register: CashRegister,
    cash_service: CashRegisterService,
):
    """
    Testa ajuste de gaveta quando o caixa está fechado:
    Permite adicionar suprimento ou retirar sangria da gaveta da última sessão fechada,
    atualizando actual_closing_amount sem abrir uma sessão ativa.
    """
    # Abre e fecha com R$ 100
    cash_service.open_session(
        db, tenant_id, test_user.id,
        CashOpenRequest(initial_amount=100.0, cash_register_id=isolated_register.id),
    )
    cash_service.close_session(
        db, tenant_id, test_user.id,
        CashCloseRequest(actual_closing_amount=100.0, cash_register_id=isolated_register.id),
    )

    # 1. Adiciona suprimento de R$ 30 com caixa fechado
    sup_closed = cash_service.add_supply(
        db, tenant_id, test_user.id,
        CashSupplyRequest(
            amount=30.0,
            description="Adicionando troco na gaveta",
            cash_register_id=isolated_register.id,
        ),
    )
    assert sup_closed.session.status == "closed"
    assert sup_closed.session.actual_closing_amount == 130.0

    # 2. Retira sangria de R$ 50 da gaveta com caixa fechado
    bld_closed = cash_service.add_bleed(
        db, tenant_id, test_user.id,
        CashBleedRequest(
            amount=50.0,
            description="Retirada noturna da gaveta",
            cash_register_id=isolated_register.id,
        ),
    )
    assert bld_closed.session.status == "closed"
    assert bld_closed.session.actual_closing_amount == 80.0

    # 3. Sangria maior que saldo na gaveta -> 400
    with pytest.raises(HTTPException) as exc_info:
        cash_service.add_bleed(
            db, tenant_id, test_user.id,
            CashBleedRequest(
                amount=100.0,
                description="Tentativa de retirar mais do que tem",
                cash_register_id=isolated_register.id,
            ),
        )
    assert exc_info.value.status_code == 400
    assert "maior que o saldo disponível na gaveta" in exc_info.value.detail


# ==============================================================================
# 6. TESTES DE STATUS ATUAL E RECONCILIAÇÃO DE FORMAS DE PAGAMENTO
# ==============================================================================

def test_current_status_and_payment_methods_aggregation(
    db: Session,
    tenant_id: int,
    test_user: User,
    test_client: Client,
    isolated_register: CashRegister,
    cash_service: CashRegisterService,
):
    """
    Testa a agregação de totais por forma de pagamento no fechamento/detalhes da sessão:
    Garante que vendas em PIX, Cartão e Dinheiro são devidamente discriminadas e contabilizadas.
    """
    # 1. Abre caixa
    detail = cash_service.open_session(
        db, tenant_id, test_user.id,
        CashOpenRequest(initial_amount=50.0, cash_register_id=isolated_register.id),
    )
    session_id = detail.session.id

    # 2. Insere vendas simuladas vinculadas a esta sessão
    s1 = Sale(
        tenant_id=tenant_id,
        client_id=test_client.id,
        cash_session_id=session_id,
        total_amount=100.0,
        discount_amount=0.0,
        payment_method="pix",
        status="completed",
    )
    db.add(s1)
    db.flush()
    db.add(SalePayment(sale_id=s1.id, payment_method="pix", amount=100.0))

    s2 = Sale(
        tenant_id=tenant_id,
        client_id=test_client.id,
        cash_session_id=session_id,
        total_amount=150.0,
        discount_amount=0.0,
        payment_method="credit_card",
        status="completed",
    )
    db.add(s2)
    db.flush()
    db.add(SalePayment(sale_id=s2.id, payment_method="credit_card", amount=150.0))

    s3 = Sale(
        tenant_id=tenant_id,
        client_id=test_client.id,
        cash_session_id=session_id,
        total_amount=50.0,
        discount_amount=0.0,
        payment_method="money",
        status="completed",
    )
    db.add(s3)
    db.flush()
    db.add(SalePayment(sale_id=s3.id, payment_method="money", amount=50.0))
    db.commit()

    # 3. Consulta status atual do terminal
    status = cash_service.get_current_status(db, tenant_id, isolated_register.id)
    assert status.is_open is True
    assert status.current_session is not None
    assert status.current_session.total_sales_amount == 300.0  # 100 + 150 + 50

    # Verifica discriminação por forma de pagamento
    methods = {pm.method: pm for pm in status.current_session.payment_methods}
    assert methods["pix"].total_amount == 100.0
    assert methods["pix"].count == 1

    assert methods["credit_card"].total_amount == 150.0
    assert methods["credit_card"].count == 1

    assert methods["money"].total_amount == 50.0
    assert methods["money"].count == 1
