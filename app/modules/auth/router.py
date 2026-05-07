from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from app.modules.auth.schemas import AuthResponse, LoginInput, MeResponse, SignupRequest
from app.modules.auth.service import AuthService, authenticate_user
from app.modules.auth.token import create_access_token, decode_token

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

@router.post("/signup", response_model=AuthResponse)
def signup(
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

    # 🍪 Setar cookies aqui
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
def login(
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
    print('userxx',result)
    # Retorno mínimo (frontend não precisa do token)
    return {
        "user": result["user"],
    }

@router.post("/refresh")
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
