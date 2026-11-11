"""认证依赖：解析 Bearer Token 并加载当前用户。"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from crud.user import get_user_by_id
from database import get_db
from models.user import User
from utils.exceptions import AppError
from utils.security import decode_token

# auto_error=False：自行抛出统一错误结构 AUTH_REQUIRED
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户（每请求查库加载角色权限，权限变更立即生效）。"""
    if not token:
        raise AppError(401, "AUTH_REQUIRED", "请先登录")
    payload = decode_token(token)
    uid = payload.get("uid")
    username = payload.get("sub")
    if uid is None or not username:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录凭证无效")
    user = await get_user_by_id(db, int(uid))
    if user is None or user.username != username:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录凭证无效")
    if not user.is_active:
        raise AppError(403, "AUTH_USER_DISABLED", "用户已被禁用")
    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        return await get_current_user(token=token, db=db)
    except AppError:
        return None
