from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, BigInteger, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class FileStatus(enum.Enum):
    DRAFT = 1        # 草稿
    PENDING_REVIEW = 2  # 待审核
    PENDING_APPROVAL = 3 # 待批准
    APPROVED = 4     # 已批准
    ARCHIVED = 5     # 已归档
    DELETED = 0      # 已删除

class ProcessFile(Base):
    __tablename__ = "process_files"

    id = Column(Integer, primary_key=True, index=True)
    file_number = Column(String(50), unique=True, index=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(20))
    version = Column(String(20), nullable=False)
    process_step = Column(String(100), nullable=False)
    
    uploader_id = Column(Integer, ForeignKey("users.id"))
    creator_id = Column(Integer, ForeignKey("users.id"))
    
    initial_upload_time = Column(DateTime, nullable=False, default=func.now())
    last_update_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    file_size = Column(BigInteger)
    storage_path = Column(String(500), nullable=False)
    
    file_status = Column(Enum(FileStatus), default=FileStatus.DRAFT)
    current_approver_id = Column(Integer, ForeignKey("users.id"))
    approval_flow = Column(Text)
    remarks = Column(Text)

    # 关系
    uploader = relationship("User", foreign_keys=[uploader_id], back_populates="uploaded_files")
    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_files")
    current_approver = relationship("User", foreign_keys=[current_approver_id])
    versions = relationship("FileVersion", back_populates="file")
    operations = relationship("FileOperationLog", back_populates="file")

class FileVersion(Base):
    __tablename__ = "file_versions"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("process_files.id"))
    version = Column(String(20), nullable=False)
    file_path = Column(String(500), nullable=False)
    uploader_id = Column(Integer, ForeignKey("users.id"))
    upload_time = Column(DateTime, nullable=False, default=func.now())
    change_description = Column(Text)
    file_size = Column(BigInteger)

    file = relationship("ProcessFile", back_populates="versions")
    uploader = relationship("User")

class FileOperationLog(Base):
    __tablename__ = "file_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("process_files.id"))
    operator_id = Column(Integer, ForeignKey("users.id"))
    operation_type = Column(String(50), nullable=False)
    operation_time = Column(DateTime, nullable=False, default=func.now())
    operation_details = Column(Text)
    ip_address = Column(String(45))

    file = relationship("ProcessFile", back_populates="operations")
    operator = relationship("User")

class ApprovalFlow(Base):
    __tablename__ = "approval_flows"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("process_files.id"))
    flow_type = Column(String(50), nullable=False)
    current_step = Column(Integer, default=1)
    status = Column(Integer, default=1)  # 1:进行中 2:已完成 0:已终止
    initiator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=func.now())
    completed_at = Column(DateTime)

    file = relationship("ProcessFile")
    initiator = relationship("User")
    steps = relationship("ApprovalStep", back_populates="flow")

class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(Integer, ForeignKey("approval_flows.id"))
    step_number = Column(Integer, nullable=False)
    step_name = Column(String(100), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"))
    approval_status = Column(Integer, default=0)  # 0:待处理 1:通过 2:驳回
    approval_time = Column(DateTime)
    approval_comment = Column(Text)

    flow = relationship("ApprovalFlow", back_populates="steps")
    approver = relationship("User")