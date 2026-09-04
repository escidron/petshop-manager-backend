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
    """Payload mínimo usado na listagem de clientes (tabela) e agendamentos.

    Inclui nome, telefone, status e nomes dos pets para permitir
    busca por pet e coluna 'Pets' na tabela — tudo em uma query só.
    Inclui campos de endereço e contatos adicionais quando disponíveis.
    """
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    is_active: bool
    created_at: datetime
    pet_names: List[str] = []

    # Endereço
    cep: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

    # Telefones adicionais
    phone_secondary_name: Optional[str] = None
    phone_secondary: Optional[str] = None
    phone_tertiary_name: Optional[str] = None
    phone_tertiary: Optional[str] = None

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
            cep=getattr(client, "cep", None),
            street=getattr(client, "street", None),
            number=getattr(client, "number", None),
            complement=getattr(client, "complement", None),
            neighborhood=getattr(client, "neighborhood", None),
            city=getattr(client, "city", None),
            state=getattr(client, "state", None),
            phone_secondary_name=getattr(client, "phone_secondary_name", None),
            phone_secondary=getattr(client, "phone_secondary", None),
            phone_tertiary_name=getattr(client, "phone_tertiary_name", None),
            phone_tertiary=getattr(client, "phone_tertiary", None),
        )
