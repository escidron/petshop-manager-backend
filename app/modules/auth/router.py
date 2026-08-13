from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, get_current_user
from app.modules.auth.schemas import (
    AuthResponse,
    LoginInput,
    MeResponse,
    SelectTenantInput,
    SwitchTenantInput,
    SignupRequest,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService, authenticate_user
from app.modules.auth.token import create_access_token, create_refresh_token, decode_token

from app.config.limiter import limiter

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

@router.post("/signup", response_model=AuthResponse)
@limiter.limit("5/minute")
def signup(
    request: Request,
    payload: SignupRequest,
    response: Response,  # 👈 adicionar
    db: Session = Depends(get_db),
):
    auth_service = AuthService()

    result = auth_service.signup(
        db=db,
        user_data=payload.user,
        tenant_data=payload.tenant,
    )

    #  Setar cookies aqui
    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=result["access_token"],
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    return result

@router.post("/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(
    request: Request,
    data: LoginInput,
    response: Response,
    db: Session = Depends(get_db),
):
    result = authenticate_user(
        db=db,
        email=data.email,
        password=data.password,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    # Usuário tem múltiplos tenants: retorna lista para o frontend escolher
    if result.get("needs_tenant_selection"):
        return result

    # Access token cookie
    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=result["access_token"],
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # Refresh token cookie
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    return {"user": result["user"]}

@router.post("/refresh")
@limiter.limit("10/minute")
def refresh_token(
    request: Request,
    response: Response,
):
    refresh_token = request.cookies.get(
        settings.COOKIE_REFRESH_NAME
    )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de atualização ausente",
        )

    payload = decode_token(refresh_token)

    if not payload or payload.get("expired"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de atualização inválido",
        )

    new_access_token = create_access_token({
        "user_id": payload["user_id"],
        "tenant_id": payload.get("tenant_id"),
        "role": payload.get("role"),
    })

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=new_access_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {"ok": True}

@router.post("/select-tenant")
@limiter.limit("10/minute")
def select_tenant(
    request: Request,
    data: SelectTenantInput,
    response: Response,
    db: Session = Depends(get_db),
):
    from app.modules.users.models import TenantUser, User

    payload = decode_token(data.selection_token)
    if not payload or payload.get("expired") or payload.get("type") != "tenant_selection":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de seleção inválido ou expirado",
        )

    user_id = int(payload["user_id"])

    tenant_user = (
        db.query(TenantUser)
        .filter(
            TenantUser.user_id == user_id,
            TenantUser.tenant_id == data.tenant_id,
            TenantUser.active == True,
        )
        .first()
    )
    if not tenant_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado a este tenant",
        )

    user = db.query(User).filter(User.id == user_id).first()

    token_data = {
        "user_id": str(user_id),
        "tenant_id": str(data.tenant_id),
        "role": tenant_user.role,
    }

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=create_access_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=create_refresh_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    return {
        "user": {
            "id": str(user_id),
            "role": tenant_user.role,
            "tenant_id": str(data.tenant_id),
            "name": user.name,
        }
    }


@router.post("/switch-tenant")
@limiter.limit("20/minute")
def switch_tenant(
    request: Request,
    data: SwitchTenantInput,
    response: Response,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    from app.modules.users.models import TenantUser

    user = context["user"]

    tenant_user = (
        db.query(TenantUser)
        .filter(
            TenantUser.user_id == user.id,
            TenantUser.tenant_id == data.tenant_id,
            TenantUser.active == True,
        )
        .first()
    )
    if not tenant_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado a este tenant",
        )

    token_data = {
        "user_id": str(user.id),
        "tenant_id": str(data.tenant_id),
        "role": tenant_user.role,
    }

    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=create_access_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=create_refresh_token(token_data),
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    return {
        "user": {
            "id": str(user.id),
            "role": tenant_user.role,
            "tenant_id": str(data.tenant_id),
            "name": user.name,
        }
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    return {"ok": True}

@router.get("/logout")
def logout_get(response: Response):
    """
    Versão GET do logout para permitir limpeza de cookies via link direto.
    """
    response.delete_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )
    return {"ok": True, "message": "Sessão limpa com sucesso. Você pode tentar o login agora."}

@router.get("/me", response_model=MeResponse)
def me(current_data: dict = Depends(get_current_tenant)):
    return current_data

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    auth_service = AuthService()
    # Pega o base_url do header Referer ou do Origin para o link do frontend
    origin = request.headers.get("origin") or "http://localhost:5173"
    auth_service.forgot_password(db, payload.email, origin)
    return {"message": "Se o e-mail existir, um link de recuperação foi enviado."}

@router.post("/verify-otp")
@limiter.limit("5/minute")
def verify_otp(
    request: Request,
    payload: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    auth_service = AuthService()
    auth_service.verify_otp(db, payload.email, payload.otp_code)
    return {"message": "Código válido."}

@router.post("/reset-password")
@limiter.limit("3/minute")
def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    auth_service = AuthService()
    auth_service.reset_password(db, payload.email, payload.otp_code, payload.new_password)
    return {"message": "Senha alterada com sucesso."}


@router.post("/verify-email")
@limiter.limit("5/minute")
def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    auth_service = AuthService()
    auth_service.verify_email(db, current_user.id, payload.otp_code)
    return {"message": "E-mail verificado com sucesso."}


@router.post("/resend-verification")
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    auth_service = AuthService()
    auth_service.resend_verification_email(db, current_user.id)
    return {"message": "E-mail de verificação enviado."}

