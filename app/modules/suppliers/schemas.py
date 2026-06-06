from pydantic import BaseModel, ConfigDict
from typing import Optional


class SupplierBase(BaseModel):
    name: str
    cnpj: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    email: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    email: Optional[str] = None


class SupplierResponse(SupplierBase):
    id: int
    tenant_id: int

    model_config = ConfigDict(from_attributes=True)
