"""审批视图接口：/api/approvals。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import crud.approval as approval_crud
import crud.file as file_crud
from crud.user import has_any_permission, has_permission, is_admin
from database import get_db
from dependencies.auth import get_current_user
from dependencies.permissions import can_view_file
from models.user import User
from utils.exceptions import AppError, forbidden_permission, validation_error
from utils.pagination import (
    check_sort,
    normalize_page,
    page_result,
    parse_int_list,
)
from utils.serializers import flow_detail, flow_summary, pending_item

router = APIRouter()


@router.get("/pending")
async def pending_list(
    type_filter: str = Query("all", alias="type", description="review / approve / all"),
    keyword: Optional[str] = Query(None),
    page: int = Query(1),
    size: int = Query(10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的待办：分配给当前用户且处于当前步骤的待处理审批。"""
    if type_filter not in ("review", "approve", "all"):
        raise validation_error("type", "type 必须是 review/approve/all")
    if type_filter == "review":
        if not has_permission(current_user, "review"):
            raise forbidden_permission("review")
    elif type_filter == "approve":
        if not has_permission(current_user, "approve"):
            raise forbidden_permission("approve")
    elif not has_any_permission(current_user, "review", "approve"):
        raise forbidden_permission("review", "approve")
    page, size = normalize_page(page, size)
    rows, total = await approval_crud.pending_items(
        db,
        current_user=current_user,
        type_filter=type_filter,
        keyword=keyword,
        page=page,
        size=size,
    )
    items = [pending_item(flow, step, file) for flow, step, file in rows]
    return page_result(items, total, page, size)


@router.get("/flows")
async def flow_list(
    file_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="逗号分隔流程状态 0,1,2"),
    page: int = Query(1),
    size: int = Query(10),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """审批流程列表（默认只返回可见文件对应流程）。"""
    page, size = normalize_page(page, size)
    check_sort(sort, ("created_at",), "created_at", order)
    statuses = parse_int_list(status, "status")
    flows, total = await file_crud.list_flows(
        db,
        current_user=current_user,
        page=page,
        size=size,
        file_id=file_id,
        statuses=statuses,
    )
    return page_result([flow_summary(item) for item in flows], total, page, size)


@router.get("/flows/{flow_id}")
async def flow_detail_endpoint(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """审批流程详情（含步骤与签名）。"""
    flow = await file_crud.get_flow_by_id(db, flow_id)
    if flow is None:
        raise AppError(404, "FLOW_NOT_FOUND", "审批流程不存在")
    allowed = can_view_file(flow.file, current_user) or is_admin(current_user)
    if not allowed:
        allowed = flow.initiator_id == current_user.id or any(
            step.approver_id == current_user.id for step in flow.steps
        )
    if not allowed:
        raise AppError(404, "FLOW_NOT_FOUND", "审批流程不存在")
    signatures = await file_crud.get_signatures(db, flow.file_id)
    return flow_detail(
        flow, [item for item in signatures if item.version == flow.version]
    )
