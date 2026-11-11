"""系统共享枚举与常量定义。

文件状态在数据库、ORM、Pydantic、前端中统一使用 int 值。
"""
from __future__ import annotations

from enum import IntEnum


class FileStatus(IntEnum):
    """工艺文件状态（全系统唯一口径）。"""

    DELETED = 0  # 已删除（软删除）
    DRAFT = 1  # 草稿
    PENDING_REVIEW = 2  # 待审核
    PENDING_APPROVAL = 3  # 待批准
    APPROVED = 4  # 已批准
    ARCHIVED = 5  # 已归档


FILE_STATUS_LABELS = {
    FileStatus.DELETED: "已删除",
    FileStatus.DRAFT: "草稿",
    FileStatus.PENDING_REVIEW: "待审核",
    FileStatus.PENDING_APPROVAL: "待批准",
    FileStatus.APPROVED: "已批准",
    FileStatus.ARCHIVED: "已归档",
}

ALIVE_STATUSES = [
    FileStatus.DRAFT,
    FileStatus.PENDING_REVIEW,
    FileStatus.PENDING_APPROVAL,
    FileStatus.APPROVED,
    FileStatus.ARCHIVED,
]


def status_label(status: int) -> str:
    """把状态值转换为中文标签。"""
    try:
        return FILE_STATUS_LABELS[FileStatus(int(status))]
    except (ValueError, KeyError):
        return "未知状态"


class ApprovalStepStatus(IntEnum):
    """审批步骤状态。"""

    PENDING = 0  # 待处理
    PASSED = 1  # 通过
    REJECTED = 2  # 驳回


APPROVAL_STEP_STATUS_LABELS = {
    ApprovalStepStatus.PENDING: "待处理",
    ApprovalStepStatus.PASSED: "通过",
    ApprovalStepStatus.REJECTED: "驳回",
}


def step_status_label(value: int) -> str:
    try:
        return APPROVAL_STEP_STATUS_LABELS[ApprovalStepStatus(int(value))]
    except (ValueError, KeyError):
        return "未知状态"


class ApprovalFlowStatus(IntEnum):
    """审批流程状态。"""

    TERMINATED = 0  # 已终止（驳回）
    IN_PROGRESS = 1  # 进行中
    COMPLETED = 2  # 已完成


APPROVAL_FLOW_STATUS_LABELS = {
    ApprovalFlowStatus.TERMINATED: "已终止",
    ApprovalFlowStatus.IN_PROGRESS: "进行中",
    ApprovalFlowStatus.COMPLETED: "已完成",
}


def flow_status_label(value: int) -> str:
    try:
        return APPROVAL_FLOW_STATUS_LABELS[ApprovalFlowStatus(int(value))]
    except (ValueError, KeyError):
        return "未知状态"


class RoleCode:
    """内置角色标识（对应 roles.name）。"""

    ADMIN = "admin"
    ENGINEER = "engineer"
    LEADER = "leader"
    MANAGER = "manager"
    ARCHIVIST = "archivist"


class PermissionCode:
    """权限代码（9 个）。"""

    UPLOAD = "upload"
    UPDATE = "update"
    DELETE = "delete"
    REVIEW = "review"
    APPROVE = "approve"
    REJECT = "reject"
    ARCHIVE = "archive"
    CATALOG_MANAGE = "catalog_manage"
    USER_MANAGE = "user_manage"


class OperationType:
    """操作日志类型（与 API 契约 §0.6.5 一致）。"""

    UPLOAD = "upload"
    UPDATE = "update"
    SUBMIT_REVIEW = "submit_review"
    REVIEW_PASS = "review_pass"
    REVIEW_REJECT = "review_reject"
    APPROVE_PASS = "approve_pass"
    APPROVE_REJECT = "approve_reject"
    ARCHIVE = "archive"
    DELETE = "delete"
    DOWNLOAD = "download"
    LOGIN = "login"
    REGISTER = "register"
    CHANGE_PASSWORD = "change_password"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DISABLE = "user_disable"
    ROLE_UPDATE = "role_update"
    CATALOG_REFRESH = "catalog_refresh"


OPERATION_TYPE_LABELS = {
    OperationType.UPLOAD: "上传",
    OperationType.UPDATE: "更新",
    OperationType.SUBMIT_REVIEW: "提交审核",
    OperationType.REVIEW_PASS: "审核通过",
    OperationType.REVIEW_REJECT: "审核驳回",
    OperationType.APPROVE_PASS: "批准通过",
    OperationType.APPROVE_REJECT: "批准驳回",
    OperationType.ARCHIVE: "归档",
    OperationType.DELETE: "删除",
    OperationType.DOWNLOAD: "下载",
    OperationType.LOGIN: "登录",
    OperationType.REGISTER: "注册",
    OperationType.CHANGE_PASSWORD: "修改密码",
    OperationType.USER_CREATE: "创建用户",
    OperationType.USER_UPDATE: "更新用户",
    OperationType.USER_DISABLE: "禁用用户",
    OperationType.ROLE_UPDATE: "角色变更",
    OperationType.CATALOG_REFRESH: "清单刷新",
}


def operation_label(operation_type: str) -> str:
    """操作类型中文标签。"""
    return OPERATION_TYPE_LABELS.get(operation_type, operation_type)


class CatalogUpdateWay:
    """文件清单刷新方式。"""

    MANUAL = "manual"  # 手动
    AUTO = "auto"  # 自动（归档触发/每日 0 点）


CATALOG_UPDATE_WAY_LABELS = {
    CatalogUpdateWay.MANUAL: "手动",
    CatalogUpdateWay.AUTO: "自动",
}


def catalog_update_way_label(value: str) -> str:
    return CATALOG_UPDATE_WAY_LABELS.get(value, value)


# 角色中文名映射（用于签名文案）
ROLE_DISPLAY_NAMES = {
    RoleCode.ADMIN: "管理员",
    RoleCode.ENGINEER: "工艺员",
    RoleCode.LEADER: "组长",
    RoleCode.MANAGER: "主管",
    RoleCode.ARCHIVIST: "资料员",
}
