from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, List

from models.user import User
from schemas.user import UserCreate, UserUpdate
from utils.security import get_password_hash  # 只导入这个函数，避免循环

class UserCRUD:
    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        result = db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    def get_user_by_employee_id(db: Session, employee_id: str) -> Optional[User]:
        result = db.execute(select(User).where(User.employee_id == employee_id))
        return result.scalar_one_or_none()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        result = db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            employee_id=user_data.employee_id,
            username=user_data.username,
            password_hash=hashed_password,
            real_name=user_data.real_name,
            department=user_data.department,
            position=user_data.position
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def update_user(db: Session, user_id: int, update_data: UserUpdate) -> Optional[User]:
        user = UserCRUD.get_user_by_id(db, user_id)
        if user:
            update_dict = update_data.dict(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(user, field, value)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        result = db.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

user_crud = UserCRUD()