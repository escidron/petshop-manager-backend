from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

from app.modules.tenant_services.schemas import ServiceResponse
from app.modules.products.schemas import ProductResponse

class PackageItemBase(BaseModel):
    service_id: Optional[int] = None
    product_id: Optional[int] = None
    quantity: int = Field(default=1, gt=0)

class PackageItemCreate(PackageItemBase):
    pass

class PackageItem(PackageItemBase):
    id: int
    package_id: int
    service: Optional[ServiceResponse] = None
    product: Optional[ProductResponse] = None

    model_config = ConfigDict(from_attributes=True)

class PackageBase(BaseModel):
    name: str
    description: Optional[str] = None
    price_cents: int
    validity_days: Optional[int] = None
    is_active: bool = True

class PackageCreate(PackageBase):
    items: List[PackageItemCreate]

class PackageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_cents: Optional[int] = None
    validity_days: Optional[int] = None
    is_active: Optional[bool] = None
    items: Optional[List[PackageItemCreate]] = None

class Package(PackageBase):
    id: int
    tenant_id: int
    items: List[PackageItem]

    model_config = ConfigDict(from_attributes=True)
