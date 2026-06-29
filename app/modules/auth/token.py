from datetime import datetime, timedelta
from typing import Dict, Any

from jose import ExpiredSignatureError, jwt, JWTError
from passlib.context import CryptContext

from app.config.settings import settings

ALGORITHM = "HS256"

pwd_context = CryptContext(
    schemes=["argon2"],  # trocar para argon2
    deprecated="auto"
)
# -------- Password --------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# -------- JWT --------

def _create_token(data: Dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: Dict[str, Any], expires_delta: int = None) -> str:
    delta = (
        timedelta(minutes=expires_delta)
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return _create_token(data, delta)


def create_selection_token(user_id: int) -> str:
    """Short-lived token (5 min) used during multi-tenant selection flow."""
    return _create_token(
        {"user_id": str(user_id), "type": "tenant_selection"},
        timedelta(minutes=5),
    )


def create_refresh_token(data: Dict[str, Any]) -> str:
    return _create_token(
        data,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except ExpiredSignatureError:
        return {"expired": True}
    except JWTError:
        return {}
