from pydantic import BaseModel
from typing import Optional


class PetBase(BaseModel):
    name: str
    species: str
    breed: Optional[str] = None
    age: Optional[int] = None
    is_active: bool = True


class PetCreate(PetBase):
    client_id: int


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    age: Optional[int] = None
    is_active: Optional[bool] = None


class PetResponse(PetBase):
    id: int
    client_id: int

    class Config:
        from_attributes = True
