from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, field_serializer

from app.utils.timezone import to_brazil_datetime


class PetBase(BaseModel):
    name: str
    species: str

    # básicos
    breed: Optional[str] = None
    gender: Optional[str] = "unknown"
    is_neutered: Optional[bool] = None

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
    is_deceased: bool = False



class PetCreate(PetBase):
    client_id: int


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    is_neutered: Optional[bool] = None

    size: Optional[str] = None
    coat_type: Optional[str] = None
    coat_color: Optional[str] = None

    age: Optional[int] = None
    age_unit: Optional[str] = None
    birth_date: Optional[date] = None


    notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_deceased: Optional[bool] = None


class PetPhotoResponse(BaseModel):
    id: int
    pet_id: int
    photo_url: str
    is_profile: bool
    category: str
    created_at: datetime

    class Config:
        from_attributes = True


class PetResponse(PetBase):
    id: int
    client_id: int
    owner_name: Optional[str]
    photos: List[PetPhotoResponse] = []

    class Config:
        from_attributes = True


class ClientPetReportItem(BaseModel):
    pet_id: int
    pet_name: str
    species: str
    species_label: str
    breed: Optional[str] = None
    gender: Optional[str] = None
    gender_label: str
    size: Optional[str] = None
    coat_type: Optional[str] = None
    coat_type_label: Optional[str] = None
    coat_color: Optional[str] = None
    is_neutered: Optional[bool] = None
    age: Optional[int] = None
    age_unit: Optional[str] = None
    age_unit_label: Optional[str] = None
    birth_date: Optional[date] = None
    is_active: bool
    is_deceased: bool
    notes: Optional[str] = None

    # Dados do Dono / Cliente
    client_id: int
    client_name: str
    client_phone: Optional[str] = None
    client_phone_secondary: Optional[str] = None

    # Último Serviço
    last_service_date: Optional[datetime] = None
    last_service_name: Optional[str] = None

    @field_serializer("last_service_date")
    def serialize_last_service_date(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

    class Config:
        from_attributes = True


class ClientPetReportResponse(BaseModel):
    items: List[ClientPetReportItem]
    total: int
    total_active_pets: int
    total_unique_clients: int

