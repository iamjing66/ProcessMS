"""文件清单请求模型：刷新接口无请求体（保留空模型便于扩展）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CatalogRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
