from pydantic import BaseModel, EmailStr, Field

# ----------------- Base -----------------
class UserBase(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    name: str = Field(..., max_length=100)
    is_active: bool = True
    role: str = Field("owner", max_length=20)
    email_verified: bool = False

# ----------------- Criação -----------------
class UserCreate(UserBase):
    password: str = Field(..., max_length=100)  # necessário só na criação

# ----------------- Resposta -----------------
class UserResponse(UserBase):
    id: int
    permissions: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True  # Pydantic v2: popula a partir de atributos de ORM

# ----------------- Alterar Senha -----------------
class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=100)
    new_password: str = Field(..., max_length=100)


class UserUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    email: EmailStr | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)

