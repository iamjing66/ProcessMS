"""用户管理接口：/api/users。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from crud.user import (
    count_active_admins,
    create_user,
    get_role_by_name,
    get_user_by_id,
    get_user_by_employee_id,
    get_user_by_username,
    has_permission,
    list_roles_by_ids,
    list_users,
    set_user_roles,
)
from database import get_db
from dependencies.auth import get_current_user
from dependencies.permissions import require_permission
from models.enums import OperationType
from models.user import User
from schemas.user import RoleIdsRequest, UserCreateRequest, UserUpdateRequest
from utils.exceptions import AppError, forbidden_permission
from utils.logging_utils import add_operation_log
from utils.pagination import check_sort, normalize_page, page_result
from utils.security import hash_password, validate_password
from utils.serializers import user_item
from utils.time import utcnow

router = APIRouter()

USER_SORT_FIELDS = ("created_at", "last_login", "employee_id")


async def _validate_role_ids(db: AsyncSession, role_ids) -> list:
    roles = await list_roles_by_ids(db, role_ids or [])
    if len({role.id for role in roles}) != len({int(item) for item in (role_ids or [])}):
        raise AppError(404, "ROLE_NOT_FOUND", "角色不存在")
    return roles


@router.get("")
async def list_user_endpoint(
    page: int = Query(1, description="页码"),
    size: int = Query(10, description="每页条数"),
    keyword: Optional[str] = Query(None, description="工号/用户名/姓名模糊"),
    is_active: Optional[bool] = Query(None),
    role: Optional[str] = Query(None, description="角色名"),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """用户列表（分页）。"""
    page, size = normalize_page(page, size)
    sort, order = check_sort(sort, USER_SORT_FIELDS, "created_at", order)
    users, total = await list_users(
        db,
        page=page,
        size=size,
        keyword=keyword,
        is_active=is_active,
        role_name=role,
        sort=sort,
        order=order,
    )
    return page_result([user_item(item) for item in users], total, page, size)


@router.post("", status_code=201)
async def create_user_endpoint(
    payload: UserCreateRequest,
    request: Request,
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """创建用户（可指定角色）。"""
    validate_password(payload.password)
    username = payload.username.strip()
    employee_id = payload.employee_id.strip()
    if await get_user_by_username(db, username) is not None:
        raise AppError(409, "DUPLICATE_USERNAME", "用户名已存在")
    if await get_user_by_employee_id(db, employee_id) is not None:
        raise AppError(409, "DUPLICATE_EMPLOYEE_ID", "工号已存在")
    await _validate_role_ids(db, payload.role_ids)
    user = await create_user(
        db,
        employee_id=employee_id,
        username=username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name.strip(),
        department=payload.department,
        position=payload.position,
        is_active=payload.is_active,
    )
    if payload.role_ids:
        await set_user_roles(db, user.id, payload.role_ids)
    await add_operation_log(
        db,
        operation_type=OperationType.USER_CREATE,
        target_type="user",
        target_id=user.id,
        operator_id=current_user.id,
        details=f"创建用户：{username}（{user.real_name}）",
        request=request,
    )
    await db.commit()
    user = await get_user_by_id(db, user.id)
    return user_item(user)


@router.get("/{user_id}")
async def get_user_endpoint(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户详情（本人或 user_manage）。"""
    if current_user.id != user_id and not has_permission(current_user, "user_manage"):
        raise forbidden_permission("user_manage")
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "用户不存在")
    return user_item(user)


@router.put("/{user_id}")
async def update_user_endpoint(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """更新用户信息/角色/启用状态。"""
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "用户不存在")
    if payload.is_active is False and user.id == current_user.id:
        raise AppError(409, "CANNOT_DISABLE_SELF", "不能禁用自己的账号")
    if payload.role_ids is not None:
        await _validate_role_ids(db, payload.role_ids)
    if payload.real_name is not None:
        user.real_name = payload.real_name.strip()
    if payload.department is not None:
        user.department = payload.department
    if payload.position is not None:
        user.position = payload.position
    if payload.is_active is not None:
        user.is_active = payload.is_active
    user.updated_at = utcnow()
    if payload.role_ids is not None:
        await set_user_roles(db, user.id, payload.role_ids)
    await db.flush()
    if await count_active_admins(db) == 0:
        raise AppError(409, "LAST_ADMIN_PROTECTED", "系统至少保留一个启用的管理员")
    await add_operation_log(
        db,
        operation_type=(
            OperationType.USER_DISABLE
            if payload.is_active is False
            else OperationType.USER_UPDATE
        ),
        target_type="user",
        target_id=user.id,
        operator_id=current_user.id,
        details=f"更新用户：{user.username}",
        request=request,
    )
    await db.commit()
    user = await get_user_by_id(db, user.id)
    return user_item(user)


@router.put("/{user_id}/roles")
async def set_roles_endpoint(
    user_id: int,
    payload: RoleIdsRequest,
    request: Request,
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """整体替换用户角色集合（传空数组=清空）。"""
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "用户不存在")
    await _validate_role_ids(db, payload.role_ids)
    await set_user_roles(db, user.id, payload.role_ids)
    user.updated_at = utcnow()
    await db.flush()
    if await count_active_admins(db) == 0:
        raise AppError(409, "LAST_ADMIN_PROTECTED", "系统至少保留一个启用的管理员")
    await add_operation_log(
        db,
        operation_type=OperationType.ROLE_UPDATE,
        target_type="user",
        target_id=user.id,
        operator_id=current_user.id,
        details=f"变更用户角色：{user.username}",
        request=request,
    )
    await db.commit()
    user = await get_user_by_id(db, user.id)
    return user_item(user)


@router.delete("/{user_id}")
async def disable_user_endpoint(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """禁用用户（软删除）。"""
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "用户不存在")
    if user.id == current_user.id:
        raise AppError(409, "CANNOT_DISABLE_SELF", "不能禁用自己的账号")
    user.is_active = False
    user.updated_at = utcnow()
    await db.flush()
    if await count_active_admins(db) == 0:
        raise AppError(409, "LAST_ADMIN_PROTECTED", "系统至少保留一个启用的管理员")
    await add_operation_log(
        db,
        operation_type=OperationType.USER_DISABLE,
        target_type="user",
        target_id=user.id,
        operator_id=current_user.id,
        details=f"禁用用户：{user.username}",
        request=request,
    )
    await db.commit()
    return {"message": "用户已禁用", "id": user.id}
