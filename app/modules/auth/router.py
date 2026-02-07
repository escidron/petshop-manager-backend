from fastapi import APIRouter, Depends, Response, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.database import get_db
from app.modules.auth.schemas import LoginInput
from app.modules.auth.service import authenticate_user

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

    # Retorno mínimo (frontend não precisa do token)
    return {
        "user": result["user"],
    }
