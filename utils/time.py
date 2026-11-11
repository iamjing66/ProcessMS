"""时间工具：统一「数据库存 UTC naive，响应输出 ISO8601 +00:00」。

这样 MySQL DATETIME 与 SQLite 行为一致，避免 8 小时时区偏差。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import settings


def utcnow() -> datetime:
    """当前 UTC 时间（naive，用于数据库存储）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: Optional[datetime]) -> Optional[str]:
    """把数据库时间序列化为 ISO8601 字符串（带 +00:00）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# 无 tzdata 的裸 Windows 环境下 ZoneInfo 不可用，使用固定偏移兜底
_CST_FALLBACK_NAMES = {
    "Asia/Shanghai",
    "Asia/Chongqing",
    "Asia/Harbin",
    "Asia/Urumqi",
    "PRC",
    "Asia/Hong_Kong",
    "Asia/Macau",
    "Asia/Taipei",
}


def _fallback_tz(name: str):
    """时区兜底：中国常用时区用固定 +08:00，其余用 UTC。"""
    if name in _CST_FALLBACK_NAMES:
        return timezone(timedelta(hours=8))
    return timezone.utc


def business_tz():
    """业务时区（默认 Asia/Shanghai，可通过 CATALOG_TZ 覆盖）。"""
    try:
        return ZoneInfo(settings.CATALOG_TZ)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return _fallback_tz(settings.CATALOG_TZ)


def business_now() -> datetime:
    """业务时区当前时间（aware）。"""
    return datetime.now(timezone.utc).astimezone(business_tz())


def to_business(dt: Optional[datetime]) -> Optional[datetime]:
    """数据库 UTC naive 时间转换为业务时区时间。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(business_tz())


def format_cn(dt: Optional[datetime]) -> str:
    """格式化为「2026-11-10 10:00」（业务时区），用于签名文案。"""
    converted = to_business(dt)
    if converted is None:
        return ""
    return converted.strftime("%Y-%m-%d %H:%M")


def parse_date(value: Optional[str], field: str = "date") -> Optional[date]:
    """解析 YYYY-MM-DD 日期字符串。"""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        from utils.exceptions import validation_error

        raise validation_error(field, "日期格式应为 YYYY-MM-DD")


def day_range_utc(
    start: Optional[date], end: Optional[date]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """把业务时区的日期区间转换为 UTC naive 时间区间 [start, end_exclusive)。

    例：Asia/Shanghai 的 2026-11-11 00:00 = UTC 2026-11-10 16:00。
    """
    tz = business_tz()
    start_dt = None
    end_dt = None
    if start is not None:
        start_dt = (
            datetime.combine(start, datetime.min.time(), tzinfo=tz)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
    if end is not None:
        end_dt = (
            datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
    return start_dt, end_dt


def month_start_utc() -> datetime:
    """当月首日 00:00（UTC naive），用于「本月新增」统计。"""
    now = utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def snapshot_no_now() -> str:
    """生成清单快照编号 QD-YYYYMMDDHHMMSS（业务时区）。"""
    return "QD-" + business_now().strftime("%Y%m%d%H%M%S")
