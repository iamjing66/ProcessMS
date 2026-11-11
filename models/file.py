"""工艺文件、版本、操作日志 ORM 模型。"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base
from models.enums import FileStatus
from utils.time import utcnow


class ProcessFile(Base):
    """工艺文件主表。"""

    __tablename__ = "process_files"
    __table_args__ = (
        Index("ix_process_files_code_upload_time", "process_code", "initial_upload_time"),
        Index("ix_process_files_status_update_time", "file_status", "last_update_time"),
        Index("ix_process_files_creator", "creator_id"),
        Index("ix_process_files_file_name", "file_name"),
        Index("ix_process_files_process_step", "process_step"),
    )

    id = Column(Integer, primary_key=True, index=True)
    file_number = Column(
        String(32), unique=True, index=True, nullable=False, comment="文件编号（不可变）"
    )
    file_name = Column(String(255), nullable=False, comment="文件名称")
    name_key = Column(
        String(300),
        unique=True,
        index=True,
        nullable=True,
        comment="重名判定键 process_code:归一化名称；软删除置 NULL 允许复用",
    )
    file_type = Column(String(20), comment="扩展名（.pdf 等）")
    process_code = Column(String(8), nullable=False, index=True, comment="工序代码")
    process_step = Column(String(100), nullable=False, comment="工序名称")
    version = Column(String(20), nullable=False, default="V1.0.0", comment="当前版本")
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="上传人")
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="编制人")
    initial_upload_time = Column(
        DateTime, default=utcnow, nullable=False, index=True, comment="首次上传时间（UTC）"
    )
    last_update_time = Column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True, comment="最后更新时间（UTC）"
    )
    file_size = Column(BigInteger, comment="文件大小（字节）")
    storage_path = Column(String(500), nullable=False, comment="存储相对路径")
    file_status = Column(
        SmallInteger,
        default=int(FileStatus.DRAFT),
        nullable=False,
        index=True,
        comment="0删除/1草稿/2待审核/3待批准/4已批准/5已归档",
    )
    current_approver_id = Column(Integer, ForeignKey("users.id"), comment="当前待办审批人")
    approved_at = Column(DateTime, comment="批准通过时间（UTC），清单 approved_at 派生源")
    archived_at = Column(DateTime, comment="归档时间（UTC）")
    archived_by = Column(Integer, ForeignKey("users.id"), comment="归档人")
    deleted_at = Column(DateTime, comment="软删除时间（UTC）")
    deleted_by = Column(Integer, ForeignKey("users.id"), comment="软删除人")
    remarks = Column(Text, comment="备注")

    uploader = relationship(
        "User", foreign_keys=[uploader_id], back_populates="uploaded_files"
    )
    creator = relationship(
        "User", foreign_keys=[creator_id], back_populates="created_files"
    )
    current_approver = relationship("User", foreign_keys=[current_approver_id])
    archived_user = relationship("User", foreign_keys=[archived_by])
    deleted_user = relationship("User", foreign_keys=[deleted_by])
    versions = relationship(
        "FileVersion",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="FileVersion.upload_time.desc()",
    )
    operations = relationship("FileOperationLog", back_populates="file")
    flows = relationship(
        "ApprovalFlow", back_populates="file", order_by="ApprovalFlow.id"
    )
    signatures = relationship(
        "FileSignature", back_populates="file", order_by="FileSignature.signed_at"
    )


class FileVersion(Base):
    """文件版本历史表。"""

    __tablename__ = "file_versions"
    __table_args__ = (UniqueConstraint("file_id", "version", name="uq_file_version"),)

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        Integer, ForeignKey("process_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version = Column(String(20), nullable=False, comment="版本号 Vx.y.z")
    file_path = Column(String(500), nullable=False, comment="存储相对路径")
    file_hash = Column(String(64), comment="SHA-256")
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    upload_time = Column(DateTime, default=utcnow, nullable=False)
    change_description = Column(Text, comment="变更说明")
    file_size = Column(BigInteger, comment="文件大小（字节）")

    file = relationship("ProcessFile", back_populates="versions")
    uploader = relationship("User")


class FileOperationLog(Base):
    """文件/系统操作日志表。"""

    __tablename__ = "file_operation_logs"
    __table_args__ = (
        Index("ix_file_logs_file_time", "file_id", "operation_time"),
        Index("ix_file_logs_operator_time", "operator_id", "operation_time"),
        Index("ix_file_logs_operation_type", "operation_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("process_files.id"), nullable=True, index=True)
    target_type = Column(
        String(20), default="file", nullable=False, index=True, comment="file/user/auth/catalog"
    )
    target_id = Column(Integer, nullable=True, comment="目标对象 ID")
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    operation_type = Column(String(50), nullable=False)
    operation_time = Column(DateTime, default=utcnow, nullable=False)
    operation_details = Column(Text)
    ip_address = Column(String(45))
    user_agent = Column(String(255))

    file = relationship("ProcessFile", back_populates="operations")
    operator = relationship("User")
