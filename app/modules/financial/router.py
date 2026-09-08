from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import require_owner
from app.modules.financial.schemas import (
    DREAccountCreate,
    DREAccountUpdate,
    DREAccountResponse,
    DREEntryUpsert,
    DREEntryBatchUpsert,
    DREEntryReplicate,
    DREEntryResponse,
    DREReportResponse,
)
from app.modules.financial.operational_result_schemas import OperationalResultResponse
from app.modules.financial.payroll_schemas import (
    PayrollProfileResponse,
    PayrollProfileUpdate,
    PayrollSummaryResponse,
    PayrollSyncToDRERequest,
    PayrollSyncResponse,
)
from app.modules.financial.service import FinancialService

router = APIRouter(
    prefix="/financial/dre",
    tags=["Financial DRE"],
    dependencies=[Depends(require_owner)],
)

operational_router = APIRouter(
    prefix="/financial/operational-result",
    tags=["Financial Operational Result"],
    dependencies=[Depends(require_owner)],
)


@operational_router.get("", response_model=OperationalResultResponse)
def get_operational_result(
    request: Request,
    year: int = Query(default=datetime.now().year, ge=2000, le=2100),
    month: int = Query(default=datetime.now().month, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    Retorna a matriz operacional de serviços diários do mês, indicadores (dias úteis, ticket médio) e comparativo anual.
    Acesso restrito ao proprietário (owner).
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.get_operational_result(db, tenant_id=tenant_id, year=year, month=month)


@operational_router.get("/export")
def export_operational_result_excel(
    request: Request,
    year: int = Query(default=datetime.now().year, ge=2000, le=2100),
    month: int = Query(default=datetime.now().month, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    Exporta a planilha de Resultado Operacional em formato Excel (.xlsx).
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    file_bytes = service.export_operational_result_excel(db, tenant_id=tenant_id, year=year, month=month)

    filename = f"Resultado_Operacional_{month:02d}_{year}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return Response(
        content=file_bytes.getvalue(),
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("", response_model=DREReportResponse)
def get_dre_report(
    request: Request,
    year: int = Query(default=datetime.now().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    """
    Retorna o relatório DRE completo de 12 meses, acumulado e indicadores gerenciais.
    Acesso restrito exclusivamente ao proprietário (owner) do pet shop.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.get_dre_report(db, tenant_id=tenant_id, year=year)


@router.post("/entries", response_model=DREEntryResponse)
def upsert_entry(
    request: Request,
    payload: DREEntryUpsert,
    db: Session = Depends(get_db),
):
    """
    Lança ou atualiza o valor de uma despesa/receita em um determinado mês de competência.
    """
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    service = FinancialService()
    try:
        entry = service.upsert_entry(
            db=db,
            tenant_id=tenant_id,
            account_id=payload.account_id,
            year=payload.competence_year,
            month=payload.competence_month,
            amount=payload.amount,
            notes=payload.notes,
            user_id=user_id,
        )
        return entry
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/entries/batch", response_model=List[DREEntryResponse])
def batch_upsert_entries(
    request: Request,
    payload: DREEntryBatchUpsert,
    db: Session = Depends(get_db),
):
    """
    Lança ou atualiza múltiplos valores de uma só vez (ex: várias contas no mesmo mês ou ano).
    """
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    service = FinancialService()
    try:
        return service.batch_upsert_entries(
            db=db,
            tenant_id=tenant_id,
            entries=payload.entries,
            user_id=user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/entries/replicate", response_model=List[DREEntryResponse])
def replicate_entry(
    request: Request,
    payload: DREEntryReplicate,
    db: Session = Depends(get_db),
):
    """
    Replica rapidamente um valor para múltiplos meses do ano (ex: Jan a Dez).
    """
    tenant_id = request.state.tenant_user.tenant_id
    user_id = request.state.tenant_user.user_id
    service = FinancialService()
    try:
        entries = service.replicate_entry(
            db=db,
            tenant_id=tenant_id,
            data=payload,
            user_id=user_id,
        )
        return entries
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/accounts", response_model=List[DREAccountResponse])
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Lista todas as contas e categorias do plano de contas gerencial DRE do pet shop.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.list_accounts(db, tenant_id=tenant_id)


@router.post("/accounts", response_model=DREAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    request: Request,
    payload: DREAccountCreate,
    db: Session = Depends(get_db),
):
    """
    Cria uma nova conta ou categoria personalizada para o pet shop.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.create_account(db, tenant_id=tenant_id, data=payload)


@router.put("/accounts/{account_id}", response_model=DREAccountResponse)
def update_account(
    request: Request,
    account_id: int,
    payload: DREAccountUpdate,
    db: Session = Depends(get_db),
):
    """
    Atualiza uma conta existente (nome, código, grupo, ordem, status).
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    account = service.update_account(
        db, tenant_id=tenant_id, account_id=account_id, data=payload
    )
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada",
        )
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db),
):
    """
    Remove uma conta personalizada. Contas protegidas do sistema não podem ser removidas.
    """
    tenant_id = request.state.tenant_user.tenant_id
    try:
        success = service.delete_account(db, tenant_id=tenant_id, account_id=account_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível excluir esta conta (ou ela pertence às regras do sistema).",
            )
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/export")
def export_dre_excel(
    request: Request,
    year: int = Query(default=datetime.now().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    """
    Exporta o relatório DRE do ano em planilha Excel (.xlsx) formatada profissionalmente.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    file_bytes = service.export_dre_excel(db, tenant_id=tenant_id, year=year)

    filename = f"DRE_{year}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return Response(content=file_bytes.getvalue(), headers=headers, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── ROUTER DE GESTÃO DA FOLHA DE PAGAMENTO, SALÁRIOS & BENEFÍCIOS ─────────────
payroll_router = APIRouter(
    prefix="/financial/payroll",
    tags=["Financial Payroll"],
    dependencies=[Depends(require_owner)],
)


@payroll_router.get("/profiles", response_model=List[PayrollProfileResponse])
def get_payroll_profiles(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Lista todos os colaboradores do pet shop com seus perfis salariais,
    provisões de 13º e férias, FGTS, INSS e benefícios.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.get_payroll_profiles(db, tenant_id=tenant_id)


@payroll_router.put("/profiles/{employee_id}", response_model=PayrollProfileResponse)
def upsert_payroll_profile(
    request: Request,
    employee_id: int,
    data: PayrollProfileUpdate,
    db: Session = Depends(get_db),
):
    """
    Cria ou atualiza a remuneração, encargos e benefícios de um colaborador.
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    try:
        return service.upsert_payroll_profile(db, tenant_id=tenant_id, employee_id=employee_id, data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@payroll_router.get("/summary", response_model=PayrollSummaryResponse)
def get_payroll_summary(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Retorna o resumo consolidado da folha de pagamento da empresa
    (totais de salários, 13º, férias, FGTS, INSS, benefícios e custo mensal global).
    """
    tenant_id = request.state.tenant_user.tenant_id
    service = FinancialService()
    return service.get_payroll_summary(db, tenant_id=tenant_id)


@payroll_router.post("/sync-to-dre", response_model=PayrollSyncResponse)
def sync_payroll_to_dre(
    request: Request,
    data: PayrollSyncToDRERequest,
    db: Session = Depends(get_db),
):
    """
    Consolida o custo de pessoal de todos os colaboradores ativos e lança
    automaticamente nas contas mapeadas do DRE para os meses selecionados do ano.
    """
    tenant_id = request.state.tenant_user.tenant_id
    user_id = getattr(request.state.tenant_user, "user_id", None)
    service = FinancialService()
    try:
        return service.sync_payroll_to_dre(db, tenant_id=tenant_id, request=data, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

