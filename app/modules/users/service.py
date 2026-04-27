from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.auth.token import hash_password, verify_password
from app.modules.users.schemas import UserCreate
from .repository import UserRepository


class UserService:
    def __init__(self):
        self.repository = UserRepository()

    def create(self, db: Session, data: UserCreate):
        user_data = data.model_dump()  # Pydantic v2
        user_data["password"] = hash_password(user_data["password"])
        return self.repository.create(db, user_data)

    def get_user(self, db: Session, user_id: int):
        return self.repository.get_user(db, user_id)

    def change_password(self, db: Session, user_id: int, current_password: str, new_password: str):
        from app.modules.users.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
        if not verify_password(current_password, user.password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta")
        user.password = hash_password(new_password)
        db.commit()

