"""权限校验依赖与资源级校验辅助。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import Depends
from sqlalchemy import or_, select

from crud.user import has_any_permission, has_permission, is_admin
from dependencies.auth import get_current_user
from models.approval import ApprovalFlow, ApprovalStep
from models.enums import (
    ApprovalFlowStatus,
    ApprovalStepStatus,
    FileStatus,
)
from models.file import ProcessFile
from models.user import User
from utils.exceptions import AppError, forbidden_permission


def require_permission(*codes: str):
    """依赖工厂：要求全部权限（admin 短路放行）。"""

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, *codes):
            raise forbidden_permission(*codes)
        return current_user

    return dependency


def require_any_permission(*codes: str):
    """依赖工厂：要求具备其中任意一个权限。"""

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_any_permission(current_user, *codes):
            raise forbidden_permission(*codes)
        return current_user

    return dependency


def ensure_owner_or_admin(file: ProcessFile, current_user: User, code: str = "NOT_FILE_OWNER") -> None:
    """资源级校验：本人（creator/uploader）或 admin。"""
    if is_admin(current_user):
        return
    if file.creator_id == current_user.id or file.uploader_id == current_user.id:
        return
    raise AppError(403, code, "只能操作本人创建的文件")


def visibility_condition(current_user: User):
    """构造文件列表可见性 SQL 条件；admin 返回 None（不过滤）。"""
    if is_admin(current_user):
        return None
    pending_file_ids = (
        select(ApprovalFlow.file_id)
        .join(ApprovalStep, ApprovalStep.flow_id == ApprovalFlow.id)
        .where(
            ApprovalFlow.status == int(ApprovalFlowStatus.IN_PROGRESS),
            ApprovalStep.approver_id == current_user.id,
            ApprovalStep.approval_status == int(ApprovalStepStatus.PENDING),
            ApprovalFlow.current_step == ApprovalStep.step_number,
        )
    )
    return or_(
        ProcessFile.file_status.in_(
            [int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)]
        ),
        ProcessFile.creator_id == current_user.id,
        ProcessFile.uploader_id == current_user.id,
        ProcessFile.id.in_(pending_file_ids),
    )


def _active_flow(file: ProcessFile) -> Optional[ApprovalFlow]:
    """取该文件进行中的审批流程（文件详情已预加载 flows）。"""
    for flow in file.flows:
        if int(flow.status) == int(ApprovalFlowStatus.IN_PROGRESS):
            return flow
    return None


def _step_approver_id(flow: Optional[ApprovalFlow], step_number: int) -> Optional[int]:
    if flow is None:
        return None
    for step in flow.steps:
        if step.step_number == step_number:
            return step.approver_id
    return None


def can_view_file(file: ProcessFile, current_user: User) -> bool:
    """文件可见性规则（API 契约 §0.7 / PLAN §10.3）。"""
    status = int(file.file_status)
    if status == int(FileStatus.DELETED):
        return False
    if is_admin(current_user):
        return True
    if status in (int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)):
        return True
    if file.creator_id == current_user.id or file.uploader_id == current_user.id:
        return True
    flow = _active_flow(file)
    if flow is not None:
        for step in flow.steps:
            if step.approver_id == current_user.id:
                return True
    return False


def is_pending_approver(file: ProcessFile, current_user: User, step_number: int) -> bool:
    """当前用户是否为进行中流程指定步骤的待处理审批人。"""
    flow = _active_flow(file)
    if flow is None or int(flow.current_step) != step_number:
        return False
    for step in flow.steps:
        if (
            step.step_number == step_number
            and step.approver_id == current_user.id
            and int(step.approval_status) == int(ApprovalStepStatus.PENDING)
        ):
            return True
    return False


def compute_allowed_actions(file: ProcessFile, current_user: User) -> List[str]:
    """按权限 + 资源状态 + 本人/审批人实时计算 allowed_actions。"""
    status = int(file.file_status)
    if status == int(FileStatus.DELETED):
        return []
    admin = is_admin(current_user)
    owner = file.creator_id == current_user.id or file.uploader_id == current_user.id
    can_update = has_permission(current_user, "update")
    can_delete = has_permission(current_user, "delete")
    actions: List[str] = []

    if can_update and (owner or admin) and status in (
        int(FileStatus.DRAFT),
        int(FileStatus.APPROVED),
        int(FileStatus.ARCHIVED),
    ):
        actions.append("update")
    if (
        can_delete
        and (admin or (owner and status == int(FileStatus.DRAFT)))
        and status not in (
            int(FileStatus.PENDING_REVIEW),
            int(FileStatus.PENDING_APPROVAL),
        )
    ):
        actions.append("delete")
    if can_update and (owner or admin) and status == int(FileStatus.DRAFT):
        actions.append("submit_review")
    if status == int(FileStatus.PENDING_REVIEW) and is_pending_approver(
        file, current_user, 1
    ) and has_permission(current_user, "review"):
        actions.append("review")
    if status == int(FileStatus.PENDING_APPROVAL) and is_pending_approver(
        file, current_user, 2
    ) and has_permission(current_user, "approve"):
        actions.append("approve")
    if has_permission(current_user, "archive") and status == int(FileStatus.APPROVED):
        actions.append("archive")
    return actions
