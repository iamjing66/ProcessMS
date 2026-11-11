"""文件清单接口：/api/catalogs。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import services.catalog_service as catalog_crud
from database import get_db
from dependencies.auth import get_current_user
from dependencies.permissions import require_permission
from models.user import User
from utils.exceptions import AppError, validation_error
from utils.pagination import check_sort, normalize_page, page_result
from utils.serializers import catalog_item, snapshot_item
from utils.time import day_range_utc, parse_date

router = APIRouter()


@router.get("")
async def list_catalogs(
    page: int = Query(1),
    size: int = Query(10),
    keyword: Optional[str] = Query(None),
    process_step: Optional[str] = Query(None),
    snapshot_id: Optional[int] = Query(None),
    sort: str = Query("file_number"),
    order: str = Query("asc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询文件清单（默认最新快照，可分页/检索）。"""
    page, size = normalize_page(page, size, default_size=20)
    sort, order = check_sort(sort, ("file_number", "approved_at"), "file_number", order)
    if snapshot_id is not None:
        snapshot = await catalog_crud.get_snapshot_by_id(db, snapshot_id)
        if snapshot is None:
            raise AppError(404, "CATALOG_NOT_FOUND", "文件清单不存在")
    else:
        snapshot = await catalog_crud.get_latest_snapshot(db)
    if snapshot is None:
        result = page_result([], 0, page, size)
        result["snapshot"] = None
        return result
    items, total = await catalog_crud.list_catalog_items(
        db,
        snapshot_id=snapshot.id,
        page=page,
        size=size,
        keyword=keyword,
        process_step=process_step,
        sort=sort,
        order=order,
    )
    time_map = await catalog_crud.approved_time_map(
        db, [item.file_id for item in items]
    )
    result = page_result(
        [catalog_item(item, time_map.get(item.file_id)) for item in items],
        total,
        page,
        size,
    )
    result["snapshot"] = snapshot_item(snapshot)
    return result


@router.post("/refresh")
async def refresh_catalog_endpoint(
    current_user: User = Depends(require_permission("catalog_manage")),
    db: AsyncSession = Depends(get_db),
):
    """手动刷新文件清单（全量生成新快照，供前端按钮调用）。"""
    snapshot = await catalog_crud.refresh_catalog(
        db, refresh_type="manual", operator_id=current_user.id
    )
    await db.commit()
    return {
        "message": "文件清单已刷新",
        "snapshot": snapshot_item(snapshot),
    }


@router.get("/snapshots")
async def list_snapshots_endpoint(
    page: int = Query(1),
    size: int = Query(10),
    refresh_type: Optional[str] = Query(None, description="manual / auto"),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清单快照历史（分页）。"""
    page, size = normalize_page(page, size)
    if refresh_type is not None and refresh_type not in ("manual", "auto"):
        raise validation_error("refresh_type", "refresh_type 必须是 manual 或 auto")
    start_date = parse_date(date_start, "date_start")
    end_date = parse_date(date_end, "date_end")
    start_dt, end_dt = day_range_utc(start_date, end_date)
    snapshots, total = await catalog_crud.list_snapshots(
        db,
        page=page,
        size=size,
        refresh_type=refresh_type,
        date_start=start_dt,
        date_end=end_dt,
    )
    return page_result([snapshot_item(item) for item in snapshots], total, page, size)


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot_endpoint(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """指定快照详情（条目不分页）。"""
    snapshot = await catalog_crud.get_snapshot_by_id(db, snapshot_id)
    if snapshot is None:
        raise AppError(404, "CATALOG_NOT_FOUND", "文件清单不存在")
    items = await catalog_crud.get_all_items(db, snapshot.id)
    time_map = await catalog_crud.approved_time_map(
        db, [item.file_id for item in items]
    )
    return {
        "snapshot": snapshot_item(snapshot),
        "items": [catalog_item(item, time_map.get(item.file_id)) for item in items],
    }
