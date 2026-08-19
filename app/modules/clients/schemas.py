from datetime import date, datetime
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any


class ClientBase(BaseModel):
    name: str
    email: Optional[str] = None
    is_active: bool = True

    document_type: Optional[str] = None
    document: Optional[str] = None
    birth_date: Optional[date] = None

    
    phone: str

    phone_secondary_name: Optional[str] = None
    phone_secondary: Optional[str] = None

    phone_tertiary_name: Optional[str] = None
    phone_tertiary: Optional[str] = None

    # Endereço
    cep: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

    # Redes sociais
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    x: Optional[str] = None


class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None

    document_type: Optional[str] = None
    document: Optional[str] = None
    birth_date: Optional[date] = None
    phone: Optional[str] = None

    phone_secondary_name: Optional[str] = None
    phone_secondary: Optional[str] = None

    phone_tertiary_name: Optional[str] = None
    phone_tertiary: Optional[str] = None

    cep: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

    instagram: Optional[str] = None
    facebook: Optional[str] = None
    x: Optional[str] = None

class ClientResponse(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ClientSummaryResponse(BaseModel):
    """Payload mínimo usado na listagem de clientes (tabela).

    Inclui nome, telefone, status e nomes dos pets para permitir
    busca por pet e coluna 'Pets' na tabela — tudo em uma query só.
    """
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    is_active: bool
    created_at: datetime
    pet_names: List[str] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_client(cls, client: Any) -> "ClientSummaryResponse":
        pets = getattr(client, "pets", []) or []
        return cls(
            id=client.id,
            name=client.name,
            phone=client.phone,
            email=client.email,
            is_active=client.is_active,
            created_at=client.created_at,
            pet_names=[p.name for p in pets if p.name and not p.is_deceased],
        )
