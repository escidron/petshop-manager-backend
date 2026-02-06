from sqlalchemy.orm import Session
from .repository import UserRepository


class UserService:
    def __init__(self):
        self.repository = UserRepository()
    
    def create(self, db, data):
        return self.repository.create(db, data)
    
    def get_user(self, db: Session, user_id: int):
        return self.repository.get_user(db, user_id)

