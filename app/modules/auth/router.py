from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from app.modules.auth.schemas import LoginInput
from app.modules.auth.service import authenticate_user
from app.modules.auth.token import create_access_token, decode_token

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


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
            detail="Invalid credentials",
        )

    # Access token cookie
    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=result["access_token"],
        httponly=True,
        secure=True,        # em dev local pode ser False
        samesite="lax",
        path="/",
    )

    # Refresh token cookie
    response.set_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        value=result["refresh_token"],
        httponly=True,
        secure=True,        # em dev local pode ser False
        samesite="lax",
        path="/",
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
            detail="Refresh token missing",
        )

    payload = decode_token(refresh_token)

    if not payload or payload.get("expired"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
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
        secure=True,      # False em dev
        samesite="lax",
        path="/",
    )

    return {"ok": True}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        path="/",
    )
    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path="/",
    )
    return {"ok": True}

@router.get("/me")
def me(current_user: dict = Depends(get_current_tenant)):
    return {"user": current_user}
