from pydantic import BaseModel
from typing import Optional


class TenantBase(BaseModel):
    name: str
    type_id: int = 1
    is_active: bool = True
    phone:str


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    type_id: Optional[int] = None
    is_active: Optional[bool] = None

class TenantTypeResponse(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True
        
class TenantResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    type: TenantTypeResponse

    class Config:
        from_attributes = True

