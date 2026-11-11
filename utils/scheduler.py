"""文件清单每日 0 点自动刷新调度器（asyncio 后台任务）。

设计要点：
- 不引入 APScheduler/Celery 等重依赖；
- next_run_at 为纯函数，便于单元测试；
- 进程内单任务，多 worker 部署时应设置 ENABLE_SCHEDULER=false。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import settings
from utils.time import utcnow

logger = logging.getLogger(__name__)

_scheduler_task: Optional[asyncio.Task] = None


def get_timezone(tz_name: Optional[str] = None):
    name = tz_name or settings.CATALOG_TZ or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        # 裸 Windows 可能没有 tzdata：中国时区固定 +08:00 兜底
        if name in ("Asia/Shanghai", "PRC", "Asia/Chongqing", "Asia/Hong_Kong"):
            logger.warning("系统缺少时区数据库，%s 使用固定 +08:00 兜底", name)
            return timezone(timedelta(hours=8))
        logger.warning("无效的时区配置 %s，回退到 UTC", name)
        return timezone.utc


def next_run_at(
    now_utc: datetime,
    tz_name: Optional[str] = None,
    hour: Optional[int] = None,
) -> datetime:
    """计算下一次刷新时间（返回 UTC naive）。

    now_utc 为 naive 时按 UTC 解释；结果始终晚于 now_utc。
    """
    tz = get_timezone(tz_name)
    refresh_hour = settings.CATALOG_REFRESH_HOUR if hour is None else hour
    refresh_hour = max(0, min(23, int(refresh_hour)))
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    local_now = now_utc.astimezone(tz)
    target_local = local_now.replace(
        hour=refresh_hour, minute=0, second=0, microsecond=0
    )
    if target_local <= local_now:
        target_local = target_local + timedelta(days=1)
    return target_local.astimezone(timezone.utc).replace(tzinfo=None)


async def refresh_catalog_once() -> None:
    """执行一次自动刷新（独立会话、独立事务）。"""
    from crud.catalog import refresh_catalog
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            snapshot = await refresh_catalog(db, refresh_type="auto", operator_id=None)
            await db.commit()
            logger.info(
                "文件清单每日自动刷新完成：%s，条目数 %s",
                snapshot.snapshot_no,
                snapshot.item_count,
            )
        except Exception:  # pragma: no cover - 依赖数据库与调度
            await db.rollback()
            logger.exception("文件清单每日自动刷新失败，将在下次触发时重试")


async def scheduler_loop() -> None:
    """调度循环：计算到下一次刷新的等待秒数，睡眠后执行。"""
    while True:
        now = utcnow()
        next_run = next_run_at(now)
        delay = max(1.0, (next_run - now).total_seconds())
        logger.info(
            "文件清单自动刷新调度已启动：下次执行时间（UTC）%s，约 %.0f 秒后",
            next_run.isoformat(),
            delay,
        )
        await asyncio.sleep(delay)
        try:
            await refresh_catalog_once()
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:  # pragma: no cover
            logger.exception("文件清单自动刷新任务异常")


def start_scheduler() -> Optional[asyncio.Task]:
    """启动调度任务（ENABLE_SCHEDULER=false 时返回 None）。"""
    global _scheduler_task
    if not settings.ENABLE_SCHEDULER:
        logger.info("ENABLE_SCHEDULER=false，未启动每日清单自动刷新任务")
        return None
    if _scheduler_task is not None and not _scheduler_task.done():
        return _scheduler_task
    _scheduler_task = asyncio.create_task(scheduler_loop(), name="catalog-scheduler")
    return _scheduler_task


async def stop_scheduler() -> None:
    """停止调度任务。"""
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:  # pragma: no cover
        pass
