"""角色与权限查询接口：/api/roles、/api/permissions。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from crud.user import list_permissions, list_roles
from database import get_db
from dependencies.permissions import require_permission
from models.user import User
from utils.serializers import permission_item, role_item

router = APIRouter()


@router.get("/roles")
async def get_roles(
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """角色列表（纯数组）。"""
    roles = await list_roles(db)
    return [role_item(role) for role in roles]


@router.get("/permissions")
async def get_permissions(
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """权限列表（纯数组）。"""
    permissions = await list_permissions(db)
    return [permission_item(item) for item in permissions]
