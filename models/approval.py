"""审批流程、审批步骤、签名 ORM 模型。"""
from __future__ import annotations

from sqlalchemy import (
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
from models.enums import ApprovalFlowStatus, ApprovalStepStatus
from utils.time import utcnow


class ApprovalFlow(Base):
    """审批流程表（每次提交审核新建一条，历史保留可追溯）。"""

    __tablename__ = "approval_flows"
    __table_args__ = (Index("ix_approval_flows_file_status", "file_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        Integer, ForeignKey("process_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version = Column(String(20), nullable=False, comment="审批针对的文件版本")
    flow_type = Column(String(20), default="standard", nullable=False)
    current_step = Column(Integer, default=1, nullable=False, comment="当前步骤序号")
    status = Column(
        SmallInteger,
        default=int(ApprovalFlowStatus.IN_PROGRESS),
        nullable=False,
        comment="0终止/1进行中/2已完成",
    )
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="发起人")
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime)
    reject_reason = Column(Text, comment="驳回原因")
    planned_approver_id = Column(
        Integer, ForeignKey("users.id"), comment="提交时预分配的主管（审核通过后生成步骤 2）"
    )

    file = relationship("ProcessFile", back_populates="flows")
    initiator = relationship("User", foreign_keys=[initiator_id])
    planned_approver = relationship("User", foreign_keys=[planned_approver_id])
    steps = relationship(
        "ApprovalStep",
        back_populates="flow",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.step_number",
    )


class ApprovalStep(Base):
    """审批步骤表。"""

    __tablename__ = "approval_steps"
    __table_args__ = (
        UniqueConstraint("flow_id", "step_number", name="uq_flow_step"),
        Index("ix_approval_steps_approver_status", "approver_id", "approval_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(
        Integer, ForeignKey("approval_flows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number = Column(Integer, nullable=False, comment="步骤序号 1审核/2批准")
    step_name = Column(String(100), nullable=False, comment="步骤名称")
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    approval_status = Column(
        SmallInteger,
        default=int(ApprovalStepStatus.PENDING),
        nullable=False,
        comment="0待处理/1通过/2驳回",
    )
    approval_time = Column(DateTime)
    approval_comment = Column(Text, comment="审批意见")

    flow = relationship("ApprovalFlow", back_populates="steps")
    approver = relationship("User", foreign_keys=[approver_id])


class FileSignature(Base):
    """签名留痕表。"""

    __tablename__ = "file_signatures"
    __table_args__ = (Index("ix_file_signatures_file_time", "file_id", "signed_at"),)

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        Integer, ForeignKey("process_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version = Column(String(20), nullable=False, comment="签名针对的版本")
    step_type = Column(String(20), nullable=False, comment="review / approve")
    step_name = Column(String(100), nullable=False, comment="组长审核 / 主管批准")
    signer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signer_name = Column(String(50), nullable=False, comment="签名时姓名快照")
    result = Column(String(10), default="pass", nullable=False, comment="pass / reject")
    signed_at = Column(DateTime, default=utcnow, nullable=False)
    remark = Column(Text, comment="签名意见")

    file = relationship("ProcessFile", back_populates="signatures")
    signer = relationship("User", foreign_keys=[signer_id])
