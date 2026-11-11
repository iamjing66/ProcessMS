"""统一业务异常与错误码。

所有业务错误通过 AppError 抛出，由 main.py 的全局异常处理器
统一输出 {code, message, detail} 结构（与 docs/API.md §0.4 一致）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """业务异常。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail or None


def validation_error(field: str, message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", "请求参数校验失败", {field: message})


def forbidden_permission(*permissions: str) -> AppError:
    codes = "、".join(permissions)
    return AppError(
        403,
        "FORBIDDEN_PERMISSION",
        f"缺少权限：{codes}",
        {"permissions": list(permissions)},
    )


def forbidden(message: str = "无权执行该操作") -> AppError:
    return AppError(403, "FORBIDDEN", message)


def not_found(code: str, message: str) -> AppError:
    return AppError(404, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)
