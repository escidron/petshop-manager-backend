from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from .schemas import UserCreate, UserResponse, PasswordChange, UserUpdate
from .service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.patch("/me", response_model=UserResponse)
def update_profile(
    data: UserUpdate,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    return service.update_user(db, context["user"].id, data)


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    service.change_password(db, context["user"].id, data.current_password, data.new_password)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    service = UserService()
    return service.get_user(db, user_id)


@router.post("/", response_model=UserResponse)
def create_client(
    data: UserCreate,
    db: Session = Depends(get_db),
):
    service = UserService()
    return service.create(db, data)