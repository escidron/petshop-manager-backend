from pydantic import BaseModel


class ServiceBase(BaseModel):
    name: str
    description: str | None = None
    duration_minutes: int
    price_cents: int
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    price_cents: int | None = None
    is_active: bool | None = None


class ServiceResponse(ServiceBase):
    id: int

    class Config:
        from_attributes = True
