"""认证相关请求模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=50)
    password: str
    real_name: str = Field(min_length=1, max_length=50)
    department: Optional[str] = Field(default=None, max_length=100)
    position: Optional[str] = Field(default=None, max_length=100)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    old_password: str
    new_password: str
