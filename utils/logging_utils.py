"""操作日志写入工具（与业务同事务，只 add 不 commit）。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.file import FileOperationLog
from utils.time import utcnow


def get_client_ip(request) -> Optional[str]:
    """获取真实客户端 IP：优先 X-Forwarded-For 首段。"""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)[:45]
    return None


def get_user_agent(request) -> Optional[str]:
    if request is None or not hasattr(request, "headers"):
        return None
    return (request.headers.get("user-agent") or "")[:255] or None


async def add_operation_log(
    db: AsyncSession,
    *,
    operation_type: str,
    target_type: str = "file",
    target_id: Optional[int] = None,
    file_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    details: Optional[str] = None,
    request=None,
) -> FileOperationLog:
    """记录一条操作日志（调用方负责 commit）。"""
    log = FileOperationLog(
        file_id=file_id,
        target_type=target_type,
        target_id=target_id,
        operator_id=operator_id,
        operation_type=operation_type,
        operation_time=utcnow(),
        operation_details=(details or "")[:2000] or None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    db.add(log)
    await db.flush()
    return log
