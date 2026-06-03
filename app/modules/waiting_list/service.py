from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import WaitingListEntry, WaitingListStatus, WaitingListItem
from .repository import WaitingListRepository
from .schemas import WaitingListEntryCreate, WaitingListEntryUpdate
from app.modules.tenant_services.models import Service

class WaitingListService:
    def __init__(self):
        self.repo = WaitingListRepository()

    def create(self, db: Session, tenant_id: int, data: WaitingListEntryCreate) -> WaitingListEntry:
        items = []
        for item_data in data.items:
            services = (
                db.query(Service)
                .filter(Service.id.in_(item_data.service_ids), Service.tenant_id == tenant_id)
                .all()
            )
            items.append(WaitingListItem(
                pet_id=item_data.pet_id,
                services=services
            ))

        entry = self.repo.create(
            db=db,
            tenant_id=tenant_id,
            client_id=data.client_id,
            preferred_date=data.preferred_date,
            preferred_period=data.preferred_period,
            notes=data.notes,
            items=items,
        )
        db.commit()
        return self.repo.get_by_id(db, tenant_id, entry.id)

    def get_all(self, db: Session, tenant_id: int, status: Optional[WaitingListStatus] = None) -> List[WaitingListEntry]:
        return self.repo.list_by_tenant(db, tenant_id, status=status)

    def update(self, db: Session, tenant_id: int, entry_id: int, data: WaitingListEntryUpdate) -> WaitingListEntry:
        entry = self.repo.get_by_id(db, tenant_id, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entrada não encontrada")

        if data.status is not None:
            entry.status = data.status
        if data.notes is not None:
            entry.notes = data.notes
        if data.preferred_date is not None:
            entry.preferred_date = data.preferred_date
        if data.preferred_period is not None:
            entry.preferred_period = data.preferred_period
        
        if data.items is not None:
            # Clear old items
            entry.items = []
            db.flush()
            
            # Add new items
            new_items = []
            for item_data in data.items:
                services = (
                    db.query(Service)
                    .filter(Service.id.in_(item_data.service_ids), Service.tenant_id == tenant_id)
                    .all()
                )
                new_items.append(WaitingListItem(
                    pet_id=item_data.pet_id,
                    services=services
                ))
            entry.items = new_items

        updated_entry = self.repo.update(db, entry)
        db.commit()
        return updated_entry

    def delete(self, db: Session, tenant_id: int, entry_id: int):
        entry = self.repo.get_by_id(db, tenant_id, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entrada não encontrada")
        self.repo.delete(db, entry)
        db.commit()

    def mark_as_scheduled(self, db: Session, tenant_id: int, entry_id: int):
        entry = self.repo.get_by_id(db, tenant_id, entry_id)
        if entry:
            entry.status = WaitingListStatus.SCHEDULED
            db.commit()
