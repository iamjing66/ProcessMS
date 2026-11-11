"""文件清单快照生成与查询（全部异步，只 flush 不 commit）。

- catalog_items 不存 approved_at：查询时由 process_files.approved_at 派生，
  缺失回退 process_files.archived_at；
- 同一秒内仅“相同刷新方式 + 相同操作人”复用快照，manual 与 auto 不互相复用。
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from crud.user import get_user_by_id
from models.catalog import CatalogItem, CatalogSnapshot
from models.enums import CatalogUpdateWay, FileStatus
from models.file import ProcessFile
from utils.exceptions import AppError
from utils.pagination import like_contains
from utils.time import snapshot_no_now, utcnow

# 进程内刷新锁：并发手动刷新返回 409 REFRESH_IN_PROGRESS
_refresh_lock = asyncio.Lock()


async def get_snapshot_by_no(
    db: AsyncSession, snapshot_no: str
) -> Optional[CatalogSnapshot]:
    result = await db.execute(
        select(CatalogSnapshot)
        .where(CatalogSnapshot.snapshot_no == snapshot_no)
        .options(selectinload(CatalogSnapshot.operator))
    )
    return result.scalar_one_or_none()


async def get_latest_snapshot(db: AsyncSession) -> Optional[CatalogSnapshot]:
    result = await db.execute(
        select(CatalogSnapshot)
        .options(selectinload(CatalogSnapshot.operator))
        .order_by(CatalogSnapshot.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_snapshot_by_id(
    db: AsyncSession, snapshot_id: int
) -> Optional[CatalogSnapshot]:
    result = await db.execute(
        select(CatalogSnapshot)
        .where(CatalogSnapshot.id == snapshot_id)
        .options(selectinload(CatalogSnapshot.operator))
    )
    return result.scalar_one_or_none()


def _is_reusable(
    snapshot: Optional[CatalogSnapshot], refresh_type: str, operator_id: Optional[int]
) -> bool:
    return (
        snapshot is not None
        and snapshot.refresh_type == refresh_type
        and snapshot.operator_id == operator_id
    )


async def _unique_snapshot_no(db: AsyncSession, base_no: str) -> str:
    """同一秒内需要新建不同语义快照时，追加序号后缀避免唯一键冲突。"""
    candidate = base_no
    index = 0
    while True:
        exists = await db.scalar(
            select(CatalogSnapshot.id).where(CatalogSnapshot.snapshot_no == candidate)
        )
        if exists is None:
            return candidate
        index += 1
        candidate = f"{base_no}-{index}"
        if index > 99:
            raise AppError(409, "REFRESH_IN_PROGRESS", "快照编号冲突，请稍后重试")


async def refresh_catalog(
    db: AsyncSession,
    *,
    refresh_type: str = CatalogUpdateWay.MANUAL,
    operator_id: Optional[int] = None,
) -> CatalogSnapshot:
    """生成新快照：当前状态为 4/5 且未删除的全部文件。"""
    base_no = snapshot_no_now()
    existing = await get_snapshot_by_no(db, base_no)
    if _is_reusable(existing, refresh_type, operator_id):
        return existing
    if _refresh_lock.locked() and refresh_type == CatalogUpdateWay.MANUAL:
        raise AppError(409, "REFRESH_IN_PROGRESS", "清单正在刷新，请稍后重试")

    async with _refresh_lock:
        existing = await get_snapshot_by_no(db, base_no)
        if _is_reusable(existing, refresh_type, operator_id):
            return existing
        snapshot_no = await _unique_snapshot_no(db, base_no)
        result = await db.execute(
            select(ProcessFile)
            .where(
                ProcessFile.file_status.in_(
                    [int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)]
                )
            )
            .options(selectinload(ProcessFile.creator))
            .order_by(ProcessFile.file_number.asc())
        )
        files = list(result.scalars().all())
        snapshot = CatalogSnapshot(
            snapshot_no=snapshot_no,
            refresh_type=refresh_type,
            operator_id=operator_id,
            item_count=0,
            created_at=utcnow(),
        )
        db.add(snapshot)
        await db.flush()
        for file in files:
            creator_name = file.creator.real_name if file.creator is not None else ""
            db.add(
                CatalogItem(
                    snapshot_id=snapshot.id,
                    file_id=file.id,
                    file_number=file.file_number,
                    file_name=file.file_name,
                    version=file.version,
                    process_code=file.process_code,
                    process_step=file.process_step,
                    creator_id=file.creator_id,
                    creator_name=creator_name,
                    file_size=file.file_size,
                    file_status=int(file.file_status),
                )
            )
        snapshot.item_count = len(files)
        await db.flush()
        if operator_id is not None:
            snapshot.operator = await get_user_by_id(db, operator_id)
        return snapshot


async def approved_time_map(
    db: AsyncSession, file_ids: List[int]
) -> Dict[int, Optional[object]]:
    """清单条目 approved_at 派生：process_files.approved_at -> archived_at -> None。"""
    if not file_ids:
        return {}
    result = await db.execute(
        select(
            ProcessFile.id,
            ProcessFile.approved_at,
            ProcessFile.archived_at,
        ).where(ProcessFile.id.in_(file_ids))
    )
    return {
        row[0]: (row[1] or row[2])
        for row in result.all()
    }


async def list_snapshots(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    refresh_type: Optional[str] = None,
    date_start=None,
    date_end=None,
) -> Tuple[List[CatalogSnapshot], int]:
    conditions = []
    if refresh_type:
        conditions.append(CatalogSnapshot.refresh_type == refresh_type)
    if date_start is not None:
        conditions.append(CatalogSnapshot.created_at >= date_start)
    if date_end is not None:
        conditions.append(CatalogSnapshot.created_at < date_end)
    total = await db.scalar(
        select(func.count(CatalogSnapshot.id)).where(*conditions)
    )
    result = await db.execute(
        select(CatalogSnapshot)
        .where(*conditions)
        .options(selectinload(CatalogSnapshot.operator))
        .order_by(CatalogSnapshot.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_catalog_items(
    db: AsyncSession,
    *,
    snapshot_id: int,
    page: int,
    size: int,
    keyword: Optional[str] = None,
    process_step: Optional[str] = None,
    sort: str = "file_number",
    order: str = "asc",
) -> Tuple[List[CatalogItem], int]:
    conditions = [CatalogItem.snapshot_id == snapshot_id]
    if keyword:
        like = like_contains(keyword)
        conditions.append(
            or_(
                CatalogItem.file_number.like(like, escape="\\"),
                CatalogItem.file_name.like(like, escape="\\"),
                CatalogItem.process_step.like(like, escape="\\"),
            )
        )
    if process_step:
        conditions.append(
            CatalogItem.process_step.like(like_contains(process_step), escape="\\")
        )
    total = await db.scalar(
        select(func.count(CatalogItem.id)).where(*conditions)
    )
    stmt = select(CatalogItem)
    if sort == "approved_at":
        stmt = stmt.join(ProcessFile, ProcessFile.id == CatalogItem.file_id)
        sort_column = func.coalesce(ProcessFile.approved_at, ProcessFile.archived_at)
    else:
        sort_column = CatalogItem.file_number
    order_by = sort_column.asc() if order == "asc" else sort_column.desc()
    result = await db.execute(
        stmt.where(*conditions)
        .order_by(order_by, CatalogItem.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def get_all_items(db: AsyncSession, snapshot_id: int) -> List[CatalogItem]:
    result = await db.execute(
        select(CatalogItem)
        .where(CatalogItem.snapshot_id == snapshot_id)
        .order_by(CatalogItem.file_number.asc(), CatalogItem.id.asc())
    )
    return list(result.scalars().all())
