"""认证接口：/api/auth。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from crud.user import (
    create_user,
    get_role_by_name,
    get_user_by_id,
    get_user_by_username,
    permission_codes,
    set_user_roles,
)
from database import get_db
from dependencies.auth import get_current_user
from models.enums import OperationType, PermissionCode
from models.user import User
from schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest
from utils.exceptions import AppError
from utils.logging_utils import add_operation_log
from utils.security import (
    create_access_token,
    hash_password,
    validate_password,
    verify_password,
)
from utils.serializers import user_item
from utils.time import utcnow

router = APIRouter()


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """JSON 登录：返回 JWT 与用户基础信息。"""
    user = await get_user_by_username(db, payload.username.strip())
    if user is None or not verify_password(payload.password, user.password_hash):
        await add_operation_log(
            db,
            operation_type=OperationType.LOGIN,
            target_type="auth",
            target_id=user.id if user else None,
            operator_id=user.id if user else None,
            details=f"登录失败：{payload.username}",
            request=request,
        )
        await db.commit()
        raise AppError(401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误")
    if not user.is_active:
        raise AppError(403, "AUTH_USER_DISABLED", "用户已被禁用")

    token = create_access_token(user.username, user.id)
    user.last_login = utcnow()
    user.updated_at = utcnow()
    await add_operation_log(
        db,
        operation_type=OperationType.LOGIN,
        target_type="auth",
        target_id=user.id,
        operator_id=user.id,
        details=f"登录成功：{user.real_name}",
        request=request,
    )
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60,
        "user": user_item(user),
    }


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """自助注册：默认分配 engineer 角色（受 ALLOW_REGISTER 开关控制）。"""
    if not settings.ALLOW_REGISTER:
        raise AppError(403, "REGISTER_DISABLED", "系统未开放自助注册")
    validate_password(payload.password)
    username = payload.username.strip()
    employee_id = payload.employee_id.strip()
    if await get_user_by_username(db, username) is not None:
        raise AppError(409, "DUPLICATE_USERNAME", "用户名已存在")
    from crud.user import get_user_by_employee_id

    if await get_user_by_employee_id(db, employee_id) is not None:
        raise AppError(409, "DUPLICATE_EMPLOYEE_ID", "工号已存在")
    engineer_role = await get_role_by_name(db, "engineer")
    if engineer_role is None:
        raise AppError(500, "INTERNAL_ERROR", "系统角色未初始化，请联系管理员")
    user = await create_user(
        db,
        employee_id=employee_id,
        username=username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name.strip(),
        department=payload.department,
        position=payload.position,
    )
    await set_user_roles(db, user.id, [engineer_role.id])
    await add_operation_log(
        db,
        operation_type=OperationType.REGISTER,
        target_type="auth",
        target_id=user.id,
        operator_id=user.id,
        details=f"注册账号：{username}",
        request=request,
    )
    await db.commit()
    user = await get_user_by_id(db, user.id)
    return user_item(user)


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    """当前登录用户信息、角色与权限码。"""
    data = user_item(current_user)
    data["permissions"] = sorted(permission_codes(current_user))
    return data


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码。"""
    user = await get_user_by_id(db, current_user.id)
    if not verify_password(payload.old_password, user.password_hash):
        raise AppError(400, "INVALID_OLD_PASSWORD", "当前密码错误")
    if payload.old_password == payload.new_password:
        raise AppError(400, "SAME_PASSWORD", "新密码不能与当前密码相同")
    validate_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = utcnow()
    await add_operation_log(
        db,
        operation_type=OperationType.CHANGE_PASSWORD,
        target_type="auth",
        target_id=user.id,
        operator_id=user.id,
        details="修改密码",
        request=request,
    )
    await db.commit()
    return {"message": "密码修改成功"}
