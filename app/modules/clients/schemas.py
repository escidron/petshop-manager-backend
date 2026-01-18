from pydantic import BaseModel, EmailStr
from typing import Optional


class ClienteBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: bool = True


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class ClienteResponse(ClienteBase):
    id: int

    class Config:
        from_attributes = True
