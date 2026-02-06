from sqlalchemy.orm import Session
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate

class UserRepository:
    def create(self, db: Session, data: UserCreate,
    ) -> User:
        user = User(**data.model_dump())
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    def get_user(self, db: Session, user_id: int):
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return {"message": "User not found"}

        return user
