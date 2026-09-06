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
from app.modules.financial.service import FinancialService

router = APIRouter(
    prefix="/financial/dre",
    tags=["Financial DRE"],
    dependencies=[Depends(require_owner)],
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
    return service.batch_upsert_entries(
        db=db,
        tenant_id=tenant_id,
        entries=payload.entries,
        user_id=user_id,
    )


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
    entries = service.replicate_entry(
        db=db,
        tenant_id=tenant_id,
        data=payload,
        user_id=user_id,
    )
    return entries


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
    service = FinancialService()
    success = service.delete_account(db, tenant_id=tenant_id, account_id=account_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir esta conta (ou ela pertence às regras do sistema).",
        )
    return None


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
