"""文件与审批动作请求模型。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SubmitReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reviewer_id: Optional[int] = None
    approver_id: Optional[int] = None
    comment: Optional[str] = Field(default=None, max_length=500)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    result: Literal["pass", "reject"]
    comment: Optional[str] = Field(default=None, max_length=500)


class ArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    comment: Optional[str] = Field(default=None, max_length=500)
