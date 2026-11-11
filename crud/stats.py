"""统计概览查询（只读）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.approval import ApprovalFlow, ApprovalStep
from models.catalog import CatalogSnapshot
from models.enums import ApprovalFlowStatus, ApprovalStepStatus, FileStatus
from models.file import FileOperationLog, ProcessFile
from models.user import User
from utils.serializers import log_item
from utils.time import iso, month_start_utc

STATUS_KEY_MAP = {
    int(FileStatus.DRAFT): "draft",
    int(FileStatus.PENDING_REVIEW): "pending_review",
    int(FileStatus.PENDING_APPROVAL): "pending_approval",
    int(FileStatus.APPROVED): "approved",
    int(FileStatus.ARCHIVED): "archived",
}


async def _pending_count(db: AsyncSession, user_id: int, step_number: int) -> int:
    stmt = (
        select(func.count(ApprovalStep.id))
        .select_from(ApprovalStep)
        .join(ApprovalFlow, ApprovalFlow.id == ApprovalStep.flow_id)
        .where(
            ApprovalStep.approver_id == user_id,
            ApprovalStep.step_number == step_number,
            ApprovalStep.approval_status == int(ApprovalStepStatus.PENDING),
            ApprovalFlow.status == int(ApprovalFlowStatus.IN_PROGRESS),
            ApprovalFlow.current_step == step_number,
        )
    )
    return int(await db.scalar(stmt) or 0)


async def build_overview(db: AsyncSession, *, current_user: User, include_users: bool) -> Dict[str, Any]:
    status_rows = await db.execute(
        select(ProcessFile.file_status, func.count(ProcessFile.id))
        .where(ProcessFile.file_status != int(FileStatus.DELETED))
        .group_by(ProcessFile.file_status)
    )
    by_status = {"draft": 0, "pending_review": 0, "pending_approval": 0, "approved": 0, "archived": 0}
    total = 0
    for status_value, count in status_rows.all():
        total += int(count)
        key = STATUS_KEY_MAP.get(int(status_value))
        if key:
            by_status[key] = int(count)

    created_this_month = int(
        await db.scalar(
            select(func.count(ProcessFile.id)).where(
                ProcessFile.file_status != int(FileStatus.DELETED),
                ProcessFile.initial_upload_time >= month_start_utc(),
            )
        )
        or 0
    )

    my_review = await _pending_count(db, current_user.id, 1)
    my_approval = await _pending_count(db, current_user.id, 2)

    latest_snapshot = await db.scalar(
        select(CatalogSnapshot).order_by(CatalogSnapshot.id.desc()).limit(1)
    )

    users_info: Optional[Dict[str, int]] = None
    if include_users:
        total_users = int(await db.scalar(select(func.count(User.id))) or 0)
        active_users = int(
            await db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
        )
        users_info = {"total": total_users, "active": active_users}

    recent_result = await db.execute(
        select(FileOperationLog)
        .options(selectinload(FileOperationLog.operator))
        .order_by(FileOperationLog.operation_time.desc(), FileOperationLog.id.desc())
        .limit(5)
    )
    recent = [log_item(item) for item in recent_result.scalars().all()]

    return {
        "files": {
            "total": total,
            "by_status": by_status,
            "created_this_month": created_this_month,
        },
        "pending": {"my_review": my_review, "my_approval": my_approval},
        "catalog": {
            "last_refresh_at": iso(latest_snapshot.created_at) if latest_snapshot else None,
            "last_snapshot_id": latest_snapshot.id if latest_snapshot else None,
            "item_count": latest_snapshot.item_count if latest_snapshot else 0,
        },
        "users": users_info,
        "recent_operations": recent,
    }
