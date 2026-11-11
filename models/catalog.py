"""文件清单快照、清单条目、文件编号流水号 ORM 模型。"""
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
from utils.time import utcnow


class CatalogSnapshot(Base):
    """文件清单刷新批次（快照元数据）。"""

    __tablename__ = "catalog_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_no = Column(String(32), unique=True, index=True, nullable=False, comment="QD-YYYYMMDDHHMMSS")
    refresh_type = Column(String(10), nullable=False, comment="manual / auto")
    operator_id = Column(Integer, ForeignKey("users.id"), comment="手动操作人；自动刷新为空")
    item_count = Column(Integer, default=0, nullable=False, comment="条目数")
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    operator = relationship("User", foreign_keys=[operator_id])
    items = relationship(
        "CatalogItem",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="CatalogItem.file_number",
    )


class CatalogItem(Base):
    """文件清单条目（归属某个快照，两步存储）。"""

    __tablename__ = "catalog_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "file_number", name="uq_catalog_item_number"),
        Index("ix_catalog_items_snapshot_number", "snapshot_id", "file_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(
        Integer,
        ForeignKey("catalog_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id = Column(Integer, ForeignKey("process_files.id"), nullable=False)
    file_number = Column(String(32), nullable=False)
    file_name = Column(String(255), nullable=False)
    version = Column(String(20), nullable=False)
    process_code = Column(String(8), nullable=False)
    process_step = Column(String(100), nullable=False)
    creator_id = Column(Integer, nullable=False)
    creator_name = Column(String(50), nullable=False)
    file_size = Column(BigInteger)
    file_status = Column(SmallInteger, nullable=False)

    snapshot = relationship("CatalogSnapshot", back_populates="items")


class FileNumberSequence(Base):
    """文件编号流水号表：(process_code, YYYYMM) 自增。"""

    __tablename__ = "file_number_sequences"
    __table_args__ = (
        UniqueConstraint("process_code", "period", name="uq_file_number_sequence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    process_code = Column(String(8), nullable=False)
    period = Column(String(6), nullable=False, comment="YYYYMM（业务时区）")
    last_seq = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
