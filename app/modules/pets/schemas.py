from datetime import date
from pydantic import BaseModel
from typing import Optional


class PetBase(BaseModel):
    name: str
    species: str

    # básicos
    breed: Optional[str] = None
    gender: Optional[str] = "unknown"

    # porte e pelagem
    size: Optional[str] = None              # PP | P | M | G | GG
    coat_type: Optional[str] = None         # short | long | double | etc
    coat_color: Optional[str] = None

    # idade
    age: Optional[int] = None
    age_unit: Optional[str] = None           # months | years
    birth_date: Optional[date] = None

    # observações
    notes: Optional[str] = None

    is_active: bool = True



class PetCreate(PetBase):
    client_id: int


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None

    size: Optional[str] = None
    coat_type: Optional[str] = None
    coat_color: Optional[str] = None

    age: Optional[int] = None
    age_unit: Optional[str] = None
    birth_date: Optional[date] = None


    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PetResponse(PetBase):
    id: int
    client_id: int
    owner_name: Optional[str]

    class Config:
        from_attributes = True
