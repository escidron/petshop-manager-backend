from pydantic import BaseModel, EmailStr


# -------- Inputs --------

class LoginInput(BaseModel):
    email: EmailStr
    password: str


# -------- Outputs --------

class UserAuthData(BaseModel):
    id: str
    role: str
    tenant_id: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserAuthData


# -------- Internal --------

class TokenPayload(BaseModel):
    user_id: str
    tenant_id: str
    role: str
