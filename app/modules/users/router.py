from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from .schemas import UserCreate, UserResponse
from .service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    service = UserService()
    return service.get_user(db, user_id)

@router.post("/",response_model=UserResponse)
def create_client(
    data: UserCreate,
    db: Session = Depends(get_db),
):
    service = UserService()
    return service.create(db, data)