from pydantic import BaseModel
from datetime import datetime
from app.enums import PetSize, PetSpecies


# =========================
# BASE
# =========================

class ServiceBase(BaseModel):
    name: str
    description: str | None = None
    species: PetSpecies | None = None
    size: PetSize | None = None
    coat_type: str | None = None
    price_cents: int
    duration_minutes: int | None = None
    is_active: bool = True


# =========================
# CREATE
# =========================

class ServiceCreate(ServiceBase):
    pass


# =========================
# UPDATE
# =========================

class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    species: PetSpecies | None = None
    size: PetSize | None = None
    coat_type: str | None = None
    price_cents: int | None = None
    duration_minutes: int | None = None
    is_active: bool | None = None


# =========================
# RESPONSE
# =========================

class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
