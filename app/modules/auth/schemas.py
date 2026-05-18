from pydantic import BaseModel, EmailStr

from app.modules.tenants.schemas import TenantCreate, TenantResponse
from app.modules.users.schemas import UserCreate, UserResponse


# -------- Inputs --------

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    user: UserCreate
    tenant: TenantCreate


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str
    

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

class MeResponse(BaseModel):
    user: UserResponse
    tenant: TenantResponse