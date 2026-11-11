"""通用请求/响应模型。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    page: int = 1
    size: int = 10


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: Optional[Dict[str, Any]] = None


class PageResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int
