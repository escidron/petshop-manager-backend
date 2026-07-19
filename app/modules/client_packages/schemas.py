from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.modules.tenant_services.schemas import ServiceResponse

class ClientPackageCreditResponse(BaseModel):
    id: int
    service_id: int | None
    service_name: str
    total_qty: int
    used_qty: int
    remaining_qty: int
    service: ServiceResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientPackageSellRequest(BaseModel):
    pet_ids: list[int]
    package_id: int

class ConsumeCreditRequest(BaseModel):
    notes: str | None = None


class ClientPackageClientInfo(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

class ClientPackagePetInfo(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class ClientPackageUsageResponse(BaseModel):
    id: int
    client_package_id: int
    credit_id: int
    change_qty: int
    notes: str | None = None
    created_at: datetime
    service_name: str | None = None
    user_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientPackageResponse(BaseModel):
    id: int
    tenant_id: int
    client_id: int
    package_id: int | None
    package_name: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    client: ClientPackageClientInfo
    pets: list[ClientPackagePetInfo]
    credits: list[ClientPackageCreditResponse]
    usages: list[ClientPackageUsageResponse] = []

    model_config = ConfigDict(from_attributes=True)
