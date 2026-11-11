"""操作日志查询参数模型（实际以 Query 参数传递）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class LogQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_id: Optional[int] = None
    operator_id: Optional[int] = None
    operation_type: Optional[str] = None
    target_type: Optional[str] = None
