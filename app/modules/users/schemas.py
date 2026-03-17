from pydantic import BaseModel, EmailStr

# ----------------- Base -----------------
class UserBase(BaseModel):
    email: EmailStr
    name: str
    is_active: bool = True
    role: str = "owner"

# ----------------- Criação -----------------
class UserCreate(UserBase):
    password: str  # necessário só na criação

# ----------------- Resposta -----------------
class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True  # Pydantic v2: popula a partir de atributos de ORM

# ----------------- Alterar Senha -----------------
class PasswordChange(BaseModel):
    current_password: str
    new_password: str
