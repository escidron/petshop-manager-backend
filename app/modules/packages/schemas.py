from pydantic import BaseModel, Field
from typing import List, Optional

class PackageItemBase(BaseModel):
    service_id: Optional[int] = None
    product_id: Optional[int] = None
    quantity: int = Field(default=1, gt=0)

class PackageItemCreate(PackageItemBase):
    pass

class PackageItem(PackageItemBase):
    id: int
    package_id: int

    class Config:
        from_attributes = True

class PackageBase(BaseModel):
    name: str
    description: Optional[str] = None
    price_cents: int
    is_active: bool = True

class PackageCreate(PackageBase):
    items: List[PackageItemCreate]

class PackageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_cents: Optional[int] = None
    is_active: Optional[bool] = None
    items: Optional[List[PackageItemCreate]] = None

class Package(PackageBase):
    id: int
    tenant_id: int
    items: List[PackageItem]

    class Config:
        from_attributes = True
