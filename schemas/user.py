"""用户管理相关请求模型。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=50)
    password: str
    real_name: str = Field(min_length=1, max_length=50)
    department: Optional[str] = Field(default=None, max_length=100)
    position: Optional[str] = Field(default=None, max_length=100)
    role_ids: List[int] = Field(default_factory=list)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    real_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    department: Optional[str] = Field(default=None, max_length=100)
    position: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class RoleIdsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role_ids: List[int] = Field(default_factory=list)
