from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    employee_id: str
    username: str
    real_name: str
    department: Optional[str] = None
    position: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    department: Optional[str] = None
    position: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    pass

class RoleResponse(RoleBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class PermissionBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None

class PermissionResponse(PermissionBase):
    id: int

    class Config:
        from_attributes = True