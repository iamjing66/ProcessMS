"""操作日志接口：/api/logs。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from crud.file import list_logs
from database import get_db
from dependencies.permissions import require_permission
from models.user import User
from utils.pagination import (
    check_sort,
    normalize_page,
    page_result,
    parse_int_list,
    parse_str_list,
)
from utils.serializers import log_item
from utils.time import day_range_utc, parse_date

router = APIRouter()


@router.get("")
async def list_logs_endpoint(
    page: int = Query(1),
    size: int = Query(10),
    file_id: Optional[int] = Query(None),
    operator_id: Optional[int] = Query(None),
    operation_type: Optional[str] = Query(None, description="逗号分隔操作类型"),
    target_type: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    sort: str = Query("operation_time"),
    order: str = Query("desc"),
    current_user: User = Depends(require_permission("user_manage")),
    db: AsyncSession = Depends(get_db),
):
    """全量操作日志（仅 user_manage）。"""
    page, size = normalize_page(page, size)
    check_sort(sort, ("operation_time",), "operation_time", order)
    operation_types = parse_str_list(operation_type)
    start_date = parse_date(date_start, "date_start")
    end_date = parse_date(date_end, "date_end")
    start_dt, end_dt = day_range_utc(start_date, end_date)
    logs, total = await list_logs(
        db,
        page=page,
        size=size,
        file_id=file_id,
        operator_id=operator_id,
        operation_types=operation_types,
        target_type=target_type,
        date_start=start_dt,
        date_end=end_dt,
        sort=sort,
        order=order,
    )
    return page_result([log_item(item) for item in logs], total, page, size)
