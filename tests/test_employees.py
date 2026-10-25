import pytest
from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.employees.service import EmployeeService
from app.modules.employees.repository import EmployeeRepository
from app.modules.employees.schemas import EmployeeCreate, EmployeeUpdate
from app.modules.employees.models import Employee, EmployeeRole


@pytest.fixture
def employee_service():
    return EmployeeService()


# ==============================================================================
# 1. TESTES DE GESTÃO DE FUNCIONÁRIOS (CRUD)
# ==============================================================================

def test_employee_crud(
    db: Session,
    tenant_id: int,
    employee_service: EmployeeService,
):
    """Testa cadastro, leitura, atualização e listagem de colaboradores."""
    # 1. Create
    emp_data = EmployeeCreate(
        name="Beatriz Tosadora",
        role="groomer",
        phone="(11) 98888-1234",
        email="beatriz.tosadora@petshop.com",
        admission_date=date(2024, 2, 1),
        is_active=True,
    )
    created = employee_service.create_employee(db, tenant_id, emp_data)
    assert created.id is not None
    assert created.name == "Beatriz Tosadora"
    assert created.role == EmployeeRole.GROOMER or created.role == "groomer"
    assert created.tenant_id == tenant_id

    # 2. Get by ID
    fetched = employee_service.get_employee(db, tenant_id, created.id)
    assert fetched.id == created.id
    assert fetched.email == "beatriz.tosadora@petshop.com"

    # 3. List
    employees = employee_service.list_employees(db, tenant_id)
    assert any(e.id == created.id for e in employees)

    # 4. Update
    update_data = EmployeeUpdate(
        name="Beatriz Lima Tosadora",
        role="bather",
        phone="(11) 99999-4321",
    )
    updated = employee_service.update_employee(db, tenant_id, created.id, update_data)
    assert updated.name == "Beatriz Lima Tosadora"
    assert updated.role == EmployeeRole.BATHER or updated.role == "bather"
    assert updated.phone == "(11) 99999-4321"


def test_get_employee_not_found_raises_404(
    db: Session,
    tenant_id: int,
    employee_service: EmployeeService,
):
    """Testa busca de colaborador inexistente retornando HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        employee_service.get_employee(db, tenant_id, 999999)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. TESTES DE TOKEN DE AGENDA PÚBLICA (regenerate_token)
# ==============================================================================

def test_regenerate_schedule_token(
    db: Session,
    tenant_id: int,
    employee_service: EmployeeService,
):
    """
    Testa a geração e renovação de token secreto de sincronização
    ou visualização de agenda do colaborador.
    """
    emp = employee_service.create_employee(
        db, tenant_id,
        EmployeeCreate(name="Carlos Banhista", role="bather", phone="(11) 91111-2222"),
    )

    # 1. Gera token
    emp_token1 = employee_service.regenerate_token(db, tenant_id, emp.id)
    token1 = emp_token1.schedule_token
    assert token1 is not None
    assert len(token1) == 32  # hex 32 chars

    # 2. Regenera token -> deve ser um novo token diferente
    emp_token2 = employee_service.regenerate_token(db, tenant_id, emp.id)
    token2 = emp_token2.schedule_token
    assert token2 is not None
    assert token2 != token1


# ==============================================================================
# 3. TESTES DE EXPORTAÇÃO PARA EXCEL
# ==============================================================================

def test_employees_export_to_excel(
    db: Session,
    tenant_id: int,
    employee_service: EmployeeService,
):
    """Testa exportação da lista de funcionários para planilha Excel."""
    excel_bytes = employee_service.export_to_excel(db, tenant_id)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0
