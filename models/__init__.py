"""模型包：显式导入全部模型，保证 Base.metadata 完整。"""
from models.enums import (
    ALIVE_STATUSES,
    APPROVAL_FLOW_STATUS_LABELS,
    APPROVAL_STEP_STATUS_LABELS,
    ApprovalFlowStatus,
    ApprovalStepStatus,
    CATALOG_UPDATE_WAY_LABELS,
    FILE_STATUS_LABELS,
    OPERATION_TYPE_LABELS,
    ROLE_DISPLAY_NAMES,
    CatalogUpdateWay,
    FileStatus,
    OperationType,
    PermissionCode,
    RoleCode,
    catalog_update_way_label,
    flow_status_label,
    operation_label,
    status_label,
    step_status_label,
)
from models.user import Permission, Role, RolePermission, User, UserRole
from models.file import FileOperationLog, FileVersion, ProcessFile
from models.approval import ApprovalFlow, ApprovalStep, FileSignature
from models.catalog import CatalogItem, CatalogSnapshot, FileNumberSequence

__all__ = [
    # 枚举与常量
    "FileStatus",
    "ApprovalFlowStatus",
    "ApprovalStepStatus",
    "PermissionCode",
    "RoleCode",
    "OperationType",
    "CatalogUpdateWay",
    "FILE_STATUS_LABELS",
    "APPROVAL_FLOW_STATUS_LABELS",
    "APPROVAL_STEP_STATUS_LABELS",
    "OPERATION_TYPE_LABELS",
    "CATALOG_UPDATE_WAY_LABELS",
    "ROLE_DISPLAY_NAMES",
    "ALIVE_STATUSES",
    "status_label",
    "step_status_label",
    "flow_status_label",
    "operation_label",
    "catalog_update_way_label",
    # 用户/权限
    "User",
    "Role",
    "UserRole",
    "Permission",
    "RolePermission",
    # 文件
    "ProcessFile",
    "FileVersion",
    "FileOperationLog",
    # 审批
    "ApprovalFlow",
    "ApprovalStep",
    "FileSignature",
    # 清单
    "CatalogSnapshot",
    "CatalogItem",
    "FileNumberSequence",
]
