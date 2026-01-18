from sqlalchemy.orm import Session
from app.modules.users.models import User

class UserRepository:
    def get_user(self, db: Session, user_id: int):
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return {"message": "User not found"}

        return user
