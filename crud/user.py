from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List
from models.user import User, Role, UserRole, Permission, RolePermission
from schemas.user import UserCreate, UserUpdate, RoleCreate
from utils.security import get_password_hash

class UserCRUD:
    async def get_user_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_by_employee_id(self, db: AsyncSession, employee_id: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.employee_id == employee_id))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, db: AsyncSession, user_data: UserCreate) -> User:
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
        await db.commit()
        await db.refresh(db_user)
        return db_user

    async def update_user(self, db: AsyncSession, user_id: int, update_data: UserUpdate) -> Optional[User]:
        user = await self.get_user_by_id(db, user_id)
        if user:
            for field, value in update_data.dict(exclude_unset=True).items():
                setattr(user, field, value)
            await db.commit()
            await db.refresh(user)
        return user

    async def get_users(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        result = await db.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

class RoleCRUD:
    async def get_role_by_name(self, db: AsyncSession, name: str) -> Optional[Role]:
        result = await db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def create_role(self, db: AsyncSession, role_data: RoleCreate) -> Role:
        db_role = Role(**role_data.dict())
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)
        return db_role

    async def get_roles(self, db: AsyncSession) -> List[Role]:
        result = await db.execute(select(Role))
        return result.scalars().all()

user_crud = UserCRUD()
role_crud = RoleCRUD()