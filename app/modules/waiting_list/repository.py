from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from .models import WaitingListEntry, WaitingListStatus, WaitingListItem

class WaitingListRepository:
    def create(self, db: Session, tenant_id: int, **kwargs) -> WaitingListEntry:
        items_data = kwargs.pop("items", [])
        entry = WaitingListEntry(tenant_id=tenant_id, **kwargs)
        entry.items = items_data
        db.add(entry)
        db.flush()
        return entry

    def get_by_id(self, db: Session, tenant_id: int, entry_id: int) -> Optional[WaitingListEntry]:
        return (
            db.query(WaitingListEntry)
            .options(
                joinedload(WaitingListEntry.client),
                joinedload(WaitingListEntry.items).joinedload(WaitingListItem.pet),
                joinedload(WaitingListEntry.items).joinedload(WaitingListItem.services),
            )
            .filter(
                WaitingListEntry.id == entry_id,
                WaitingListEntry.tenant_id == tenant_id,
            )
            .first()
        )

    def list_by_tenant(
        self, 
        db: Session, 
        tenant_id: int, 
        status: Optional[WaitingListStatus] = None
    ) -> List[WaitingListEntry]:
        query = db.query(WaitingListEntry).options(
            joinedload(WaitingListEntry.client),
            joinedload(WaitingListEntry.items).joinedload(WaitingListItem.pet),
            joinedload(WaitingListEntry.items).joinedload(WaitingListItem.services),
        ).filter(WaitingListEntry.tenant_id == tenant_id)
        
        if status:
            query = query.filter(WaitingListEntry.status == status)
            
        return query.order_by(WaitingListEntry.created_at.asc()).all()

    def update(self, db: Session, entry: WaitingListEntry) -> WaitingListEntry:
        db.flush()
        return entry

    def delete(self, db: Session, entry: WaitingListEntry):
        db.delete(entry)
        db.flush()
