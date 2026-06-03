from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_active_subscription
from .schemas import WaitingListEntryCreate, WaitingListEntryUpdate, WaitingListEntryResponse
from .service import WaitingListService
from .models import WaitingListStatus

router = APIRouter(
    prefix="/waiting-list",
    tags=["Waiting List"],
    dependencies=[Depends(get_current_tenant)],
)

@router.post("/", response_model=WaitingListEntryResponse, dependencies=[Depends(require_active_subscription)])
def create_entry(
    data: WaitingListEntryCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return WaitingListService().create(db, tenant_id, data)

@router.get("/", response_model=List[WaitingListEntryResponse])
def list_entries(
    request: Request,
    status: Optional[WaitingListStatus] = Query(None),
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return WaitingListService().get_all(db, tenant_id, status=status)

@router.patch("/{entry_id}", response_model=WaitingListEntryResponse, dependencies=[Depends(require_active_subscription)])
def update_entry(
    entry_id: int,
    data: WaitingListEntryUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    return WaitingListService().update(db, tenant_id, entry_id, data)

@router.delete("/{entry_id}", status_code=204, dependencies=[Depends(require_active_subscription)])
def delete_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id = request.state.tenant_user.tenant_id
    WaitingListService().delete(db, tenant_id, entry_id)
