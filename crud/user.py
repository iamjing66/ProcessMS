"""用户、角色、权限数据访问层（全部异步，只 flush 不 commit）。"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import Permission, Role, RolePermission, User, UserRole
from utils.pagination import like_contains
from utils.time import utcnow

# 加载用户时一次性加载角色与权限，供权限判断使用
USER_LOAD_OPTIONS = [
    selectinload(User.roles)
    .selectinload(UserRole.role)
    .selectinload(Role.permissions)
    .selectinload(RolePermission.permission)
]


def _sort_column(sort: str):
    mapping = {
        "created_at": User.created_at,
        "last_login": User.last_login,
        "employee_id": User.employee_id,
    }
    return mapping.get(sort, User.created_at)


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(*USER_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(
        select(User)
        .where(User.username == username)
        .options(*USER_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_user_by_employee_id(db: AsyncSession, employee_id: str) -> Optional[User]:
    result = await db.execute(
        select(User)
        .where(User.employee_id == employee_id)
        .options(*USER_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    employee_id: str,
    username: str,
    password_hash: str,
    real_name: str,
    department: Optional[str] = None,
    position: Optional[str] = None,
    is_active: bool = True,
) -> User:
    user = User(
        employee_id=employee_id,
        username=username,
        password_hash=password_hash,
        real_name=real_name,
        department=department,
        position=position,
        is_active=is_active,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def list_roles_by_ids(db: AsyncSession, role_ids: Sequence[int]) -> List[Role]:
    if not role_ids:
        return []
    result = await db.execute(select(Role).where(Role.id.in_(list(role_ids))))
    return list(result.scalars().all())


async def get_role_by_name(db: AsyncSession, name: str) -> Optional[Role]:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def list_roles(db: AsyncSession) -> List[Role]:
    result = await db.execute(select(Role).order_by(Role.id))
    return list(result.scalars().all())


async def list_permissions(db: AsyncSession) -> List[Permission]:
    result = await db.execute(select(Permission).order_by(Permission.id))
    return list(result.scalars().all())


async def set_user_roles(db: AsyncSession, user_id: int, role_ids: Sequence[int]) -> None:
    """整体替换用户角色集合。"""
    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    await db.flush()
    for role_id in dict.fromkeys(int(rid) for rid in role_ids):
        db.add(UserRole(user_id=user_id, role_id=role_id))
    await db.flush()


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    role_name: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
) -> Tuple[List[User], int]:
    conditions = []
    if keyword:
        like = like_contains(keyword)
        conditions.append(
            or_(
                User.username.like(like, escape="\\"),
                User.employee_id.like(like, escape="\\"),
                User.real_name.like(like, escape="\\"),
            )
        )
    if is_active is not None:
        conditions.append(User.is_active.is_(bool(is_active)))
    if role_name:
        conditions.append(
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, UserRole.role_id == Role.id)
                .where(Role.name == role_name)
            )
        )

    total = await db.scalar(select(func.count(User.id)).where(*conditions)) or 0
    column = _sort_column(sort)
    order_by = column.asc() if order == "asc" else column.desc()
    result = await db.execute(
        select(User)
        .where(*conditions)
        .options(*USER_LOAD_OPTIONS)
        .order_by(order_by, User.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().all()), int(total)


async def count_active_admins(db: AsyncSession) -> int:
    """统计启用状态且拥有 admin 角色的用户数量。"""
    stmt = (
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.is_active.is_(True), Role.name == "admin")
    )
    return int(await db.scalar(stmt) or 0)


async def find_earliest_user_with_permission(
    db: AsyncSession, permission_code: str
) -> Optional[User]:
    """自动分配审批人：最早创建的、启用且具备指定权限的用户。

    admin 作为兜底：仅当没有非 admin 候选人时才分配给 admin，
    避免默认审批人总是落到管理员账号上。
    """
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(User.is_active.is_(True), Permission.code == permission_code)
        .options(*USER_LOAD_OPTIONS)
        .order_by(User.created_at.asc(), User.id.asc())
        .limit(20)
    )
    result = await db.execute(stmt)
    candidates = list(result.scalars().unique().all())
    for candidate in candidates:
        if not any(
            link.role is not None and link.role.name == "admin"
            for link in candidate.roles
        ):
            return candidate
    return candidates[0] if candidates else None


def permission_codes(user: User) -> set[str]:
    """取用户的权限码并集。"""
    codes: set[str] = set()
    for link in user.roles:
        if link.role is None:
            continue
        for role_permission in link.role.permissions:
            if role_permission.permission is not None:
                codes.add(role_permission.permission.code)
    return codes


def is_admin(user: User) -> bool:
    return any(link.role is not None and link.role.name == "admin" for link in user.roles)


def has_permission(user: User, *codes: str) -> bool:
    """权限判断，admin 短路放行。"""
    if is_admin(user):
        return True
    owned = permission_codes(user)
    return all(code in owned for code in codes)


def has_any_permission(user: User, *codes: str) -> bool:
    if is_admin(user):
        return True
    owned = permission_codes(user)
    return any(code in owned for code in codes)
