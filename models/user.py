"""用户、角色、权限 ORM 模型。"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base
from utils.time import utcnow


class User(Base):
    """用户表。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(20), unique=True, index=True, nullable=False, comment="工号")
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 密码哈希")
    real_name = Column(String(50), nullable=False, comment="姓名")
    department = Column(String(100), comment="部门")
    position = Column(String(100), comment="职位")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    last_login = Column(DateTime, comment="最后登录时间（UTC）")
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    roles = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    uploaded_files = relationship(
        "ProcessFile",
        foreign_keys="ProcessFile.uploader_id",
        back_populates="uploader",
    )
    created_files = relationship(
        "ProcessFile",
        foreign_keys="ProcessFile.creator_id",
        back_populates="creator",
    )

    @property
    def role_names(self) -> list[str]:
        return [link.role.name for link in self.roles if link.role is not None]


class Role(Base):
    """角色表。"""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, comment="角色代码")
    description = Column(Text, comment="角色描述/中文名")
    created_at = Column(DateTime, default=utcnow, nullable=False)

    users = relationship("UserRole", back_populates="role")
    permissions = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserRole(Base):
    """用户-角色关联表。"""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users", lazy="selectin")


class Permission(Base):
    """权限表。"""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, comment="权限代码")
    name = Column(String(100), nullable=False, comment="权限名称")
    description = Column(Text, comment="权限描述")

    roles = relationship("RolePermission", back_populates="permission")


class RolePermission(Base):
    """角色-权限关联表。"""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(
        Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles", lazy="selectin")
