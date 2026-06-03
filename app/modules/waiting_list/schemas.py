from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from .models import WaitingListStatus, WaitingListPeriod
from app.modules.clients.schemas import ClientResponse
from app.modules.pets.schemas import PetResponse
from app.modules.tenant_services.schemas import ServiceResponse

class WaitingListItemBase(BaseModel):
    pet_id: int
    service_ids: List[int]

class WaitingListItemResponse(BaseModel):
    id: int
    pet_id: int
    pet: PetResponse
    services: List[ServiceResponse]

    model_config = ConfigDict(from_attributes=True)

class WaitingListEntryBase(BaseModel):
    client_id: int
    items: List[WaitingListItemBase]
    preferred_date: Optional[datetime] = None
    preferred_period: WaitingListPeriod = WaitingListPeriod.ANY
    notes: Optional[str] = None

class WaitingListEntryCreate(WaitingListEntryBase):
    pass

class WaitingListEntryUpdate(BaseModel):
    status: Optional[WaitingListStatus] = None
    notes: Optional[str] = None
    preferred_date: Optional[datetime] = None
    preferred_period: Optional[WaitingListPeriod] = None
    items: Optional[List[WaitingListItemBase]] = None

class WaitingListEntryResponse(BaseModel):
    id: int
    tenant_id: int
    client_id: int
    status: WaitingListStatus
    preferred_date: Optional[datetime]
    preferred_period: WaitingListPeriod
    notes: Optional[str]
    created_at: datetime
    
    client: ClientResponse
    items: List[WaitingListItemResponse]

    model_config = ConfigDict(from_attributes=True)
