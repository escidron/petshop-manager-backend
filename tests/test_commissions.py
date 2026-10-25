import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.commissions.service import CommissionService
from app.modules.commissions.schemas import (
    CommissionRuleCreate,
    CommissionRuleUpdate,
    CommissionPayRequest,
)
from app.modules.commissions.models import CommissionRule, CommissionEntry
from app.modules.employees.models import Employee
from app.modules.tenant_services.models import Service
from app.modules.sales.models import Sale, SaleItem


@pytest.fixture
def commission_service():
    return CommissionService()


# ==============================================================================
# 1. TESTES DE GESTÃO DE REGRAS DE COMISSÃO (CRUD & Validações)
# ==============================================================================

def test_commission_rule_crud(
    db: Session,
    tenant_id: int,
    test_employee: Employee,
    test_service: Service,
    commission_service: CommissionService,
):
    """Testa criação, leitura, atualização e exclusão de regras de comissão."""
    # 1. Cria regra percentual vinculada a funcionário e serviço
    rule_data = CommissionRuleCreate(
        name="Comissão Padrão Banho 20%",
        employee_ids=[test_employee.id],
        service_ids=[test_service.id],
        applies_to="service",
        commission_type="percentage",
        value=Decimal("20.00"),
        is_active=True,
    )
    rule = commission_service.create_rule(db, tenant_id, rule_data)
    assert rule.id is not None
    assert rule.name == "Comissão Padrão Banho 20%"
    assert rule.commission_type == "percentage"
    assert rule.value == Decimal("20.00")
    assert rule.tenant_id == tenant_id

    # 2. Busca por ID
    fetched = commission_service.get_rule(db, tenant_id, rule.id)
    assert fetched.id == rule.id

    # 3. Listagem
    rules = commission_service.list_rules(db, tenant_id)
    assert any(r.id == rule.id for r in rules)

    # 4. Atualização
    update_data = CommissionRuleUpdate(
        name="Comissão Banho Promocional 25%",
        value=Decimal("25.00"),
    )
    updated = commission_service.update_rule(db, tenant_id, rule.id, update_data)
    assert updated.name == "Comissão Banho Promocional 25%"
    assert updated.value == Decimal("25.00")

    # 5. Exclusão
    commission_service.delete_rule(db, tenant_id, rule.id)
    with pytest.raises(HTTPException) as exc_info:
        commission_service.get_rule(db, tenant_id, rule.id)
    assert exc_info.value.status_code == 404


def test_get_rule_not_found_raises_404(
    db: Session,
    tenant_id: int,
    commission_service: CommissionService,
):
    """Testa busca de regra inexistente retornando 404."""
    with pytest.raises(HTTPException) as exc_info:
        commission_service.get_rule(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE GERAÇÃO E CÁLCULO DE COMISSÕES (Percentage & Fixed com Split)
# ==============================================================================

def test_generate_commission_entry_percentage(
    db: Session,
    tenant_id: int,
    test_employee: Employee,
    test_service: Service,
    commission_service: CommissionService,
):
    """
    Testa cálculo de comissão percentual:
    Subtotal R$ 150,00 com regra de 10% -> comissão de R$ 15,00.
    """
    rule = CommissionRule(
        tenant_id=tenant_id,
        name="10% Tosa",
        applies_to="service",
        commission_type="percentage",
        value=Decimal("10.00"),
        is_active=True,
    )
    db.add(rule)
    db.flush()
    # Vincula o serviço e funcionário à regra
    rule.services.append(test_service)
    rule.employees.append(test_employee)
    db.commit()

    entry = commission_service.generate_entry(
        db=db,
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        service_id=test_service.id,
        item_type="service",
        subtotal=Decimal("150.00"),
        ref_date=date.today(),
    )

    assert entry is not None
    assert entry.status == "pending"
    assert entry.base_amount == Decimal("150.00")
    assert entry.commission_amount == Decimal("15.00")
    assert entry.rate == Decimal("10.00")
    assert entry.employee_id == test_employee.id


def test_generate_commission_entry_fixed_with_split(
    db: Session,
    tenant_id: int,
    test_employee: Employee,
    test_service: Service,
    commission_service: CommissionService,
):
    """
    Testa cálculo de comissão com valor fixo dividido entre colaboradores (split_count=2):
    Valor fixo R$ 30,00 dividido por 2 -> comissão de R$ 15,00.
    """
    rule = CommissionRule(
        tenant_id=tenant_id,
        name="Comissão Fixa R$ 30 Banho",
        applies_to="service",
        commission_type="fixed",
        value=Decimal("30.00"),
        is_active=True,
    )
    db.add(rule)
    db.flush()
    rule.services.append(test_service)
    rule.employees.append(test_employee)
    db.commit()

    entry = commission_service.generate_entry(
        db=db,
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        service_id=test_service.id,
        item_type="service",
        subtotal=Decimal("100.00"),
        ref_date=date.today(),
        split_count=2,
    )

    assert entry is not None
    assert entry.commission_amount == Decimal("15.00")  # 30 / 2
    assert entry.commission_type == "fixed"


def test_generate_retroactive_conflict_on_duplicate(
    db: Session,
    tenant_id: int,
    test_employee: Employee,
    test_service: Service,
    commission_service: CommissionService,
):
    """
    Testa geração retroativa de comissão para um item de venda:
    Se já existe comissão calculada para o item, lança HTTP 409 Conflict.
    """
    rule = CommissionRule(
        tenant_id=tenant_id,
        name="Regra Retroativa",
        applies_to="service",
        commission_type="percentage",
        value=Decimal("10.00"),
        is_active=True,
    )
    db.add(rule)
    db.flush()
    rule.services.append(test_service)
    rule.employees.append(test_employee)
    db.commit()

    # Cria uma venda e item simulados
    sale = Sale(
        tenant_id=tenant_id,
        total_amount=100.0,
        discount_amount=0.0,
        payment_method="pix",
        status="completed",
    )
    db.add(sale)
    db.flush()

    item = SaleItem(
        sale_id=sale.id,
        item_type="service",
        item_id=test_service.id,
        name=test_service.name,
        quantity=1.0,
        unit_price=100.0,
        subtotal=100.0,
    )
    db.add(item)
    db.commit()

    # 1. Primeira chamada gera a comissão normalmente
    e1 = commission_service.generate_retroactive(
        db, tenant_id, test_employee.id, test_service.id, "service",
        Decimal("100.00"), date.today(), sale_id=sale.id, sale_item_id=item.id,
    )
    assert e1 is not None

    # 2. Segunda chamada para o mesmo sale_item_id deve falhar com 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        commission_service.generate_retroactive(
            db, tenant_id, test_employee.id, test_service.id, "service",
            Decimal("100.00"), date.today(), sale_id=sale.id, sale_item_id=item.id,
        )
    assert exc_info.value.status_code == 409
    assert "Comissão já foi calculada" in exc_info.value.detail


# ==============================================================================
# 3. TESTES DE PAGAMENTO E RELATÓRIO DE COMISSÕES
# ==============================================================================

def test_pay_entries_success_and_validations(
    db: Session,
    tenant_id: int,
    test_employee: Employee,
    commission_service: CommissionService,
):
    """
    Testa o pagamento (baixa) de comissões pendentes:
    - Marca como status='paid' com timestamp e notas
    - Impede pagar comissão pertencente a outro funcionário (HTTP 400)
    - Impede pagar IDs inexistentes (HTTP 404)
    """
    # 1. Cria comissão pendente
    entry = CommissionEntry(
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        commission_type="percentage",
        rate=Decimal("10.00"),
        base_amount=Decimal("100.00"),
        commission_amount=Decimal("10.00"),
        status="pending",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # 2. Paga a comissão com sucesso
    pay_req = CommissionPayRequest(
        employee_id=test_employee.id,
        entry_ids=[entry.id],
        notes="Pagamento quinzenal via PIX",
    )
    paid = commission_service.pay_entries(db, tenant_id, pay_req)
    assert len(paid) == 1
    assert paid[0].status == "paid"
    assert paid[0].paid_at is not None
    assert paid[0].notes == "Pagamento quinzenal via PIX"

    # 3. Cria outro funcionário e tenta pagar comissão com ID de funcionário trocado -> 400
    other_emp = Employee(
        tenant_id=tenant_id,
        name="Outro Tosador",
        role="groomer",
        is_active=True,
    )
    db.add(other_emp)
    db.commit()

    entry2 = CommissionEntry(
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        commission_type="percentage",
        rate=Decimal("10.00"),
        base_amount=Decimal("50.00"),
        commission_amount=Decimal("5.00"),
        status="pending",
    )
    db.add(entry2)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        commission_service.pay_entries(
            db, tenant_id,
            CommissionPayRequest(employee_id=other_emp.id, entry_ids=[entry2.id]),
        )
    assert exc_info.value.status_code == 400
    assert "não pertence ao funcionário" in exc_info.value.detail

    # 4. Tentar pagar IDs que não existem -> 404
    with pytest.raises(HTTPException) as exc_info:
        commission_service.pay_entries(
            db, tenant_id,
            CommissionPayRequest(employee_id=test_employee.id, entry_ids=[999999]),
        )
    assert exc_info.value.status_code == 404
