"""统一分页与排序参数处理（API 契约 §0.5 / §10.1）。"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from utils.exceptions import validation_error

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 10


def _safe_int(value: Any, default: int) -> int:
    """分页参数防御：非法/超范围/非整数一律回退默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_page(page: Optional[int], size: Optional[int], default_size: int = DEFAULT_PAGE_SIZE):
    """页码与每页条数钳制：page>=1，size 1-100。"""
    page_value = _safe_int(page, 1) if page is not None else 1
    size_value = _safe_int(size, default_size) if size is not None else default_size
    if page_value < 1:
        page_value = 1
    if size_value < 1:
        size_value = 1
    if size_value > MAX_PAGE_SIZE:
        size_value = MAX_PAGE_SIZE
    return page_value, size_value


def page_result(items: List[Any], total: int, page: int, size: int) -> Dict[str, Any]:
    """构造分页信封 {items,total,page,size,pages}。"""
    pages = math.ceil(total / size) if size > 0 and total > 0 else 0
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "size": size,
        "pages": pages,
    }


def check_sort(
    sort: Optional[str],
    allowed: Sequence[str],
    default: str,
    order: Optional[str] = "desc",
) -> tuple[str, str]:
    """校验排序字段白名单与排序方向。"""
    sort_value = sort or default
    if sort_value not in allowed:
        raise validation_error("sort", f"排序字段必须是：{', '.join(allowed)}")
    order_value = (order or "desc").lower()
    if order_value not in ("asc", "desc"):
        raise validation_error("order", "排序方向必须是 asc 或 desc")
    return sort_value, order_value


def escape_like(value: str) -> str:
    """转义 LIKE 通配符（%, _, 反斜杠），防止用户输入当作通配符。"""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def like_contains(value: str) -> str:
    """构造两侧模糊匹配的 LIKE 模式（配合 escape="\\" 使用）。"""
    return f"%{escape_like(str(value).strip())}%"


def parse_int_list(value: Optional[str], field: str = "status") -> List[int]:
    """解析逗号分隔的整数列表，如 "1,2"。"""
    if value is None or str(value).strip() == "":
        return []
    result: List[int] = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            raise validation_error(field, f"{field} 必须是逗号分隔的整数")
    return result


def parse_str_list(value: Optional[str]) -> List[str]:
    """解析逗号分隔的字符串列表。"""
    if value is None or str(value).strip() == "":
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]
