from pydantic import BaseModel

class AddressResponse(BaseModel):
    cep: str
    street: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
