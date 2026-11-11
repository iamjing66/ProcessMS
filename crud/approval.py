"""审批流程状态机与查询（全部异步，只 flush 不 commit）。"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from crud.user import find_earliest_user_with_permission, get_user_by_id, has_permission
from models.approval import ApprovalFlow, ApprovalStep, FileSignature
from models.enums import (
    ApprovalFlowStatus,
    ApprovalStepStatus,
    FileStatus,
    OperationType,
    status_label,
)
from models.file import ProcessFile
from models.user import User
from utils.exceptions import AppError, validation_error
from utils.logging_utils import add_operation_log
from utils.pagination import like_contains
from utils.time import utcnow

STEP_REVIEW_NAME = "组长审核"
STEP_APPROVE_NAME = "主管批准"


async def resolve_assignee(
    db: AsyncSession, explicit_id: Optional[int], permission_code: str, field: str
) -> User:
    """确定审批人：显式指定（校验存在/启用/权限）或自动分配最早具备权限者。"""
    if explicit_id is not None:
        user = await get_user_by_id(db, int(explicit_id))
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "用户不存在")
        if not user.is_active:
            raise validation_error(field, "指定的审批人已被禁用")
        codes = set()
        for link in user.roles:
            if link.role is None:
                continue
            for rp in link.role.permissions:
                if rp.permission is not None:
                    codes.add(rp.permission.code)
        if permission_code not in codes and not any(
            link.role is not None and link.role.name == "admin" for link in user.roles
        ):
            raise validation_error(field, f"指定的审批人缺少 {permission_code} 权限")
        return user
    user = await find_earliest_user_with_permission(db, permission_code)
    if user is None:
        raise AppError(409, "NO_ELIGIBLE_APPROVER", "未找到可用的审批人，请联系管理员")
    return user


async def create_flow(
    db: AsyncSession,
    *,
    file: ProcessFile,
    initiator_id: int,
    reviewer_id: int,
    approver_id: int,
    comment: Optional[str] = None,
) -> ApprovalFlow:
    """提交审核：新建 flow（step1=组长审核），预分配主管。"""
    now = utcnow()
    flow = ApprovalFlow(
        file_id=file.id,
        version=file.version,
        flow_type="standard",
        current_step=1,
        status=int(ApprovalFlowStatus.IN_PROGRESS),
        initiator_id=initiator_id,
        created_at=now,
        planned_approver_id=approver_id,
    )
    db.add(flow)
    await db.flush()
    step1 = ApprovalStep(
        flow_id=flow.id,
        step_number=1,
        step_name=STEP_REVIEW_NAME,
        approver_id=reviewer_id,
        approval_status=int(ApprovalStepStatus.PENDING),
    )
    db.add(step1)
    await db.flush()
    return flow


async def create_signature(
    db: AsyncSession,
    *,
    file: ProcessFile,
    signer: User,
    version: str,
    step_type: str,
    step_name: str,
    result: str,
    remark: Optional[str],
) -> FileSignature:
    signature = FileSignature(
        file_id=file.id,
        version=version,
        step_type=step_type,
        step_name=step_name,
        signer_id=signer.id,
        signer_name=signer.real_name,
        result=result,
        signed_at=utcnow(),
        remark=remark,
    )
    db.add(signature)
    await db.flush()
    return signature


def _find_step(flow: ApprovalFlow, step_number: int) -> Optional[ApprovalStep]:
    for step in flow.steps:
        if step.step_number == step_number:
            return step
    return None


async def submit_for_review(
    db: AsyncSession,
    *,
    file: ProcessFile,
    initiator: User,
    reviewer: User,
    approver: User,
    comment: Optional[str],
    request=None,
) -> ApprovalFlow:
    """提交审核：文件 1 -> 2，生成 flow + 步骤 1。"""
    if int(file.file_status) != int(FileStatus.DRAFT):
        raise AppError(
            409,
            "STATE_CONFLICT",
            f"当前状态为{status_label(int(file.file_status))}，不可提交审核",
        )
    now = utcnow()
    # 条件更新：1 -> 2，保证并发重复提交只有一次成功
    update_result = await db.execute(
        update(ProcessFile)
        .where(
            ProcessFile.id == file.id,
            ProcessFile.file_status == int(FileStatus.DRAFT),
        )
        .values(
            file_status=int(FileStatus.PENDING_REVIEW),
            current_approver_id=reviewer.id,
            last_update_time=now,
        )
    )
    if not update_result.rowcount:
        raise AppError(409, "STATE_CONFLICT", "当前状态已变更，不可提交审核")
    file.file_status = int(FileStatus.PENDING_REVIEW)
    file.current_approver_id = reviewer.id
    file.last_update_time = now
    flow = await create_flow(
        db,
        file=file,
        initiator_id=initiator.id,
        reviewer_id=reviewer.id,
        approver_id=approver.id,
    )
    await add_operation_log(
        db,
        operation_type=OperationType.SUBMIT_REVIEW,
        target_type="file",
        target_id=file.id,
        file_id=file.id,
        operator_id=initiator.id,
        details=f"提交审核：{file.file_name} {flow.version}" + (f"；说明：{comment}" if comment else ""),
        request=request,
    )
    await db.flush()
    return flow


async def review_file(
    db: AsyncSession,
    *,
    file: ProcessFile,
    flow: ApprovalFlow,
    step: ApprovalStep,
    current_user: User,
    result: str,
    comment: Optional[str],
    request=None,
) -> dict:
    """审核环节：通过 -> 3（生成步骤 2）；驳回 -> 1（流程终止）。"""
    if step is None or step.approver_id != current_user.id:
        raise AppError(403, "NOT_CURRENT_APPROVER", "您不是该步骤的审批人")
    if int(step.approval_status) != int(ApprovalStepStatus.PENDING):
        raise AppError(409, "APPROVAL_ALREADY_DONE", "该审批步骤已处理")
    now = utcnow()
    passed = result == "pass"
    comment_text = (comment or "").strip() or ("同意" if passed else None)
    # 条件更新保证幂等与并发安全（只有待处理步骤能被处理）
    update_result = await db.execute(
        update(ApprovalStep)
        .where(
            ApprovalStep.id == step.id,
            ApprovalStep.approval_status == int(ApprovalStepStatus.PENDING),
        )
        .values(
            approval_status=int(
                ApprovalStepStatus.PASSED if passed else ApprovalStepStatus.REJECTED
            ),
            approval_time=now,
            approval_comment=comment_text,
        )
    )
    if not update_result.rowcount:
        raise AppError(409, "APPROVAL_ALREADY_DONE", "该审批步骤已处理")
    await db.refresh(step)
    await create_signature(
        db,
        file=file,
        signer=current_user,
        version=flow.version,
        step_type="review",
        step_name=STEP_REVIEW_NAME,
        result="pass" if passed else "reject",
        remark=comment,
    )
    next_approver: Optional[User] = None
    if passed:
        approver_id = flow.planned_approver_id
        if approver_id is not None:
            next_approver = await get_user_by_id(db, approver_id)
        # 预分配主管失效（被禁用/权限被收回）时回退自动分配
        if next_approver is not None and (
            not next_approver.is_active or not has_permission(next_approver, "approve")
        ):
            next_approver = None
        if next_approver is None:
            next_approver = await find_earliest_user_with_permission(db, "approve")
        if next_approver is None:
            raise AppError(409, "NO_ELIGIBLE_APPROVER", "未找到可用的审批人，请联系管理员")
        step2 = ApprovalStep(
            flow_id=flow.id,
            step_number=2,
            step_name=STEP_APPROVE_NAME,
            approver_id=next_approver.id,
            approval_status=int(ApprovalStepStatus.PENDING),
        )
        db.add(step2)
        flow.current_step = 2
        flow.planned_approver_id = next_approver.id
        file.file_status = int(FileStatus.PENDING_APPROVAL)
        file.current_approver_id = next_approver.id
        file.last_update_time = now
        await add_operation_log(
            db,
            operation_type=OperationType.REVIEW_PASS,
            target_type="file",
            target_id=file.id,
            file_id=file.id,
            operator_id=current_user.id,
            details=f"审核通过：{file.file_name} {flow.version}" + (f"；意见：{comment}" if comment else ""),
            request=request,
        )
    else:
        flow.status = int(ApprovalFlowStatus.TERMINATED)
        flow.completed_at = now
        flow.reject_reason = comment
        file.file_status = int(FileStatus.DRAFT)
        file.current_approver_id = None
        file.last_update_time = now
        await add_operation_log(
            db,
            operation_type=OperationType.REVIEW_REJECT,
            target_type="file",
            target_id=file.id,
            file_id=file.id,
            operator_id=current_user.id,
            details=f"审核驳回：{file.file_name} {flow.version}；意见：{comment}",
            request=request,
        )
    await db.flush()
    return {
        "passed": passed,
        "message": "审核通过，已提交主管批准" if passed else "已驳回，文件退回草稿",
        "next_approver": next_approver,
    }


async def approve_file(
    db: AsyncSession,
    *,
    file: ProcessFile,
    flow: ApprovalFlow,
    step: ApprovalStep,
    current_user: User,
    result: str,
    comment: Optional[str],
    request=None,
) -> dict:
    """批准环节：通过 -> 4（流程完成）；驳回 -> 1（流程终止）。"""
    if step is None or step.approver_id != current_user.id:
        raise AppError(403, "NOT_CURRENT_APPROVER", "您不是该步骤的审批人")
    if int(step.approval_status) != int(ApprovalStepStatus.PENDING):
        raise AppError(409, "APPROVAL_ALREADY_DONE", "该审批步骤已处理")
    now = utcnow()
    passed = result == "pass"
    comment_text = (comment or "").strip() or ("同意" if passed else None)
    update_result = await db.execute(
        update(ApprovalStep)
        .where(
            ApprovalStep.id == step.id,
            ApprovalStep.approval_status == int(ApprovalStepStatus.PENDING),
        )
        .values(
            approval_status=int(
                ApprovalStepStatus.PASSED if passed else ApprovalStepStatus.REJECTED
            ),
            approval_time=now,
            approval_comment=comment_text,
        )
    )
    if not update_result.rowcount:
        raise AppError(409, "APPROVAL_ALREADY_DONE", "该审批步骤已处理")
    await db.refresh(step)
    await create_signature(
        db,
        file=file,
        signer=current_user,
        version=flow.version,
        step_type="approve",
        step_name=STEP_APPROVE_NAME,
        result="pass" if passed else "reject",
        remark=comment,
    )
    if passed:
        flow.status = int(ApprovalFlowStatus.COMPLETED)
        flow.completed_at = now
        file.file_status = int(FileStatus.APPROVED)
        file.current_approver_id = None
        file.approved_at = now
        file.last_update_time = now
        await add_operation_log(
            db,
            operation_type=OperationType.APPROVE_PASS,
            target_type="file",
            target_id=file.id,
            file_id=file.id,
            operator_id=current_user.id,
            details=f"批准通过：{file.file_name} {flow.version}" + (f"；意见：{comment}" if comment else ""),
            request=request,
        )
    else:
        flow.status = int(ApprovalFlowStatus.TERMINATED)
        flow.completed_at = now
        flow.reject_reason = comment
        file.file_status = int(FileStatus.DRAFT)
        file.current_approver_id = None
        file.approved_at = None
        file.last_update_time = now
        await add_operation_log(
            db,
            operation_type=OperationType.APPROVE_REJECT,
            target_type="file",
            target_id=file.id,
            file_id=file.id,
            operator_id=current_user.id,
            details=f"批准驳回：{file.file_name} {flow.version}；意见：{comment}",
            request=request,
        )
    await db.flush()
    return {
        "passed": passed,
        "message": "批准通过，可归档" if passed else "已驳回，文件退回草稿",
    }


async def archive_file(
    db: AsyncSession,
    *,
    file: ProcessFile,
    current_user: User,
    comment: Optional[str],
    request=None,
) -> None:
    """归档：文件 4 -> 5。"""
    if int(file.file_status) != int(FileStatus.APPROVED):
        raise AppError(
            409,
            "STATE_CONFLICT",
            f"当前状态为{status_label(int(file.file_status))}，不可执行归档",
        )
    now = utcnow()
    file.file_status = int(FileStatus.ARCHIVED)
    file.archived_at = now
    file.archived_by = current_user.id
    file.current_approver_id = None
    file.last_update_time = now
    await add_operation_log(
        db,
        operation_type=OperationType.ARCHIVE,
        target_type="file",
        target_id=file.id,
        file_id=file.id,
        operator_id=current_user.id,
        details=f"归档文件：{file.file_name}" + (f"；说明：{comment}" if comment else ""),
        request=request,
    )
    await db.flush()


async def pending_items(
    db: AsyncSession,
    *,
    current_user: User,
    type_filter: str = "all",
    keyword: Optional[str] = None,
    page: int = 1,
    size: int = 10,
) -> Tuple[List[Tuple[ApprovalFlow, ApprovalStep, ProcessFile]], int]:
    """我的待办：分配给当前用户且为当前步骤的待处理步骤。"""
    conditions = [
        ApprovalFlow.status == int(ApprovalFlowStatus.IN_PROGRESS),
        ApprovalStep.approver_id == current_user.id,
        ApprovalStep.approval_status == int(ApprovalStepStatus.PENDING),
        ApprovalFlow.current_step == ApprovalStep.step_number,
    ]
    if type_filter == "review":
        conditions.append(ApprovalStep.step_number == 1)
    elif type_filter == "approve":
        conditions.append(ApprovalStep.step_number == 2)
    if keyword:
        like = like_contains(keyword)
        conditions.append(
            or_(
                ProcessFile.file_name.like(like, escape="\\"),
                ProcessFile.file_number.like(like, escape="\\"),
            )
        )

    base = (
        select(ApprovalFlow, ApprovalStep, ProcessFile)
        .join(ApprovalStep, ApprovalStep.flow_id == ApprovalFlow.id)
        .join(ProcessFile, ProcessFile.id == ApprovalFlow.file_id)
        .where(*conditions)
    )
    total = await db.scalar(
        select(func.count(ApprovalStep.id))
        .select_from(ApprovalStep)
        .join(ApprovalFlow, ApprovalFlow.id == ApprovalStep.flow_id)
        .join(ProcessFile, ProcessFile.id == ApprovalFlow.file_id)
        .where(*conditions)
    )
    result = await db.execute(
        base.options(
            selectinload(ApprovalFlow.initiator),
            selectinload(ApprovalFlow.file),
            selectinload(ProcessFile.creator),
            selectinload(ProcessFile.uploader),
            selectinload(ProcessFile.current_approver),
        )
        .order_by(ApprovalFlow.created_at.desc(), ApprovalStep.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = [(row[0], row[1], row[2]) for row in result.all()]
    return rows, int(total or 0)
