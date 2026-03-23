from datetime import datetime
from pydantic import BaseModel


class ClientPackageCreditResponse(BaseModel):
    id: int
    service_id: int | None
    service_name: str
    total_qty: int
    used_qty: int
    remaining_qty: int

    class Config:
        from_attributes = True


class ClientPackageSellRequest(BaseModel):
    pet_id: int
    package_id: int


class ClientPackageResponse(BaseModel):
    id: int
    tenant_id: int
    client_id: int
    pet_id: int
    package_id: int | None
    package_name: str
    is_active: bool
    created_at: datetime
    credits: list[ClientPackageCreditResponse]

    class Config:
        from_attributes = True
