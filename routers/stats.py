"""统计接口：/api/stats。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from crud.stats import build_overview
from crud.user import has_permission
from database import get_db
from dependencies.auth import get_current_user
from models.user import User

router = APIRouter()


@router.get("/overview")
async def overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """概览统计：文件状态分布、我的待办、清单最近刷新、最近操作。"""
    include_users = has_permission(current_user, "user_manage")
    return await build_overview(
        db, current_user=current_user, include_users=include_users
    )
