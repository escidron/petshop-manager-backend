from sqlalchemy.orm import Session

from app.modules.auth.token import hash_password
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

