"""文件接口：/api/files。"""
from __future__ import annotations

import time as time_module
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import crud.file as file_crud
import services.approval_service as approval_crud
from config import settings
from crud.user import has_permission, is_admin
from database import get_db
from dependencies.auth import get_current_user
from dependencies.permissions import (
    can_view_file,
    compute_allowed_actions,
    ensure_owner_or_admin,
    require_permission,
)
from models.enums import FileStatus, OperationType, status_label
from models.file import ProcessFile
from models.user import User
from schemas.file import ArchiveRequest, ReviewRequest, SubmitReviewRequest
from utils.exceptions import AppError, forbidden_permission, validation_error
from utils.file_number import normalize_process_code
from utils.file_upload import (
    build_content_disposition,
    guess_media_type,
    remove_stored_file,
    resolve_storage_path,
    save_upload_file,
)
from utils.logging_utils import add_operation_log
from utils.names import build_name_key
from utils.pagination import (
    check_sort,
    normalize_page,
    page_result,
    parse_int_list,
)
from utils.serializers import (
    file_detail,
    file_item,
    log_item,
    signature_item,
    snapshot_item,
    user_brief,
    version_item,
)
from utils.time import day_range_utc, iso, parse_date, utcnow
from utils.versioning import next_version, validate_version

router = APIRouter()

# 进程内上传冷却（同用户 UPLOAD_COOLDOWN_SECONDS 秒内重复上传返回 429）
_upload_last_at: dict[int, float] = {}


def _check_upload_cooldown(user_id: int) -> None:
    cooldown = max(0, int(settings.UPLOAD_COOLDOWN_SECONDS))
    if cooldown <= 0:
        return
    now = time_module.monotonic()
    last = _upload_last_at.get(user_id)
    if last is not None and (now - last) < cooldown:
        raise AppError(429, "RATE_LIMITED", "操作过于频繁，请稍后再试")
    _upload_last_at[user_id] = now


async def _load_visible_file(
    db: AsyncSession, file_id: int, current_user: User
) -> ProcessFile:
    """加载并对当前用户做可见性校验；不可见统一 404（避免探测）。"""
    file = await file_crud.get_file_for_detail(db, file_id)
    if (
        file is None
        or int(file.file_status) == int(FileStatus.DELETED)
        or not can_view_file(file, current_user)
    ):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")
    return file


async def _load_file_related(
    db: AsyncSession, file_id: int, current_user: User
) -> ProcessFile:
    """可见者或相关审批人/发起人可加载（用于流程/签名/日志查询）。"""
    file = await file_crud.get_file_for_detail(db, file_id)
    if file is None or int(file.file_status) == int(FileStatus.DELETED):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")
    if can_view_file(file, current_user) or is_admin(current_user):
        return file
    for flow in file.flows:
        if flow.initiator_id == current_user.id:
            return file
        for step in flow.steps:
            if step.approver_id == current_user.id:
                return file
    raise AppError(404, "FILE_NOT_FOUND", "文件不存在")


def _detail_of(file: ProcessFile, current_user: User) -> dict:
    return file_detail(
        file,
        allowed_actions=compute_allowed_actions(file, current_user),
        can_download=True,
    )


def _normalize_download_version(version: Optional[str], fallback: str) -> str:
    text = (version or "").strip()
    if not text:
        return fallback
    if text[0] in ("v", "V"):
        return "V" + text[1:]
    return "V" + text


# ---------------------------------------------------------------------------
# 上传 / 列表 / 详情
# ---------------------------------------------------------------------------
@router.post("/upload", status_code=201)
async def upload_file(
    request: Request,
    file_name: str = Form(..., description="文件名称"),
    process_step: str = Form(..., description="工序名称"),
    process_code: Optional[str] = Form(None, description="工序代码，默认 GEN"),
    version: Optional[str] = Form(None, description="初始版本号，默认 V1.0.0"),
    remarks: Optional[str] = Form(None, description="备注"),
    file: UploadFile = File(..., description="文件本体"),
    current_user: User = Depends(require_permission("upload")),
    db: AsyncSession = Depends(get_db),
):
    """上传新工艺文件（生成唯一编号，写入初始版本）。"""
    _check_upload_cooldown(current_user.id)
    name = (file_name or "").strip()
    if not name or len(name) > 255:
        raise validation_error("file_name", "文件名称长度应为 1-255 字")
    step = (process_step or "").strip()
    if not step or len(step) > 100:
        raise validation_error("process_step", "工序名称长度应为 1-100 字")
    if remarks is not None and len(remarks) > 1000:
        raise validation_error("remarks", "备注不能超过 1000 字")
    code = normalize_process_code(process_code)
    initial_version = validate_version(version) if version and version.strip() else "V1.0.0"

    name_key = build_name_key(code, name)
    if await file_crud.find_by_name_key(db, name_key):
        raise AppError(
            409,
            "FILE_NAME_DUPLICATED",
            "同一工序代码下已存在同名文件（忽略大小写/首尾空白）",
        )

    saved = await save_upload_file(file)
    try:
        file_obj = await file_crud.create_file(
            db,
            file_name=name,
            name_key=name_key,
            process_code=code,
            process_step=step,
            version=initial_version,
            uploader_id=current_user.id,
            creator_id=current_user.id,
            relative_path=saved["relative_path"],
            file_type=saved["file_type"],
            file_size=saved["file_size"],
            file_hash=saved["file_hash"],
            remarks=remarks,
        )
        await file_crud.add_file_version(
            db,
            file_obj,
            version=initial_version,
            relative_path=saved["relative_path"],
            file_hash=saved["file_hash"],
            file_size=saved["file_size"],
            uploader_id=current_user.id,
            change_description="首版上传",
        )
        await add_operation_log(
            db,
            operation_type=OperationType.UPLOAD,
            target_type="file",
            target_id=file_obj.id,
            file_id=file_obj.id,
            operator_id=current_user.id,
            details=f"上传文件：{name} {initial_version}（编号 {file_obj.file_number}）",
            request=request,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        remove_stored_file(saved["relative_path"])
        raise
    detail = await file_crud.get_file_for_detail(db, file_obj.id)
    return _detail_of(detail, current_user)


@router.get("")
async def list_files(
    page: int = Query(1),
    size: int = Query(10),
    keyword: Optional[str] = Query(None, description="名称/编号/工序/编制人模糊"),
    file_number: Optional[str] = Query(None),
    file_name: Optional[str] = Query(None),
    process_step: Optional[str] = Query(None),
    process_code: Optional[str] = Query(None),
    creator_id: Optional[int] = Query(None),
    creator_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="逗号分隔状态，如 1,2"),
    upload_date_start: Optional[str] = Query(None),
    upload_date_end: Optional[str] = Query(None),
    sort: str = Query("last_update_time"),
    order: str = Query("desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """文件列表 + 多条件检索（分页）。"""
    page, size = normalize_page(page, size)
    sort, order = check_sort(sort, file_crud.FILE_SORT_FIELDS, "last_update_time", order)
    statuses = parse_int_list(status, "status")
    start_date = parse_date(upload_date_start, "upload_date_start")
    end_date = parse_date(upload_date_end, "upload_date_end")
    start_dt, end_dt = day_range_utc(start_date, end_date)
    files, total = await file_crud.search_files(
        db,
        current_user=current_user,
        page=page,
        size=size,
        keyword=keyword,
        file_number=file_number,
        file_name=file_name,
        process_step=process_step,
        process_code=process_code,
        creator_id=creator_id,
        creator_name=creator_name,
        statuses=statuses,
        upload_date_start=start_dt,
        upload_date_end=end_dt,
        sort=sort,
        order=order,
    )
    return page_result([file_item(item) for item in files], total, page, size)


@router.get("/{file_id}")
async def get_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """文件详情（含 allowed_actions / approval / signatures）。"""
    file = await _load_visible_file(db, file_id, current_user)
    return _detail_of(file, current_user)


# ---------------------------------------------------------------------------
# 更新 / 删除
# ---------------------------------------------------------------------------
@router.put("/{file_id}")
async def update_file(
    file_id: int,
    request: Request,
    file_name: Optional[str] = Form(None),
    process_step: Optional[str] = Form(None),
    process_code: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    new_file: Optional[UploadFile] = File(None),
    version_type: Optional[str] = Form(None),
    change_description: Optional[str] = Form(None),
    current_user: User = Depends(require_permission("update")),
    db: AsyncSession = Depends(get_db),
):
    """更新文件元数据或上传新版本（状态 2/3 锁定）。"""
    file = await _load_visible_file(db, file_id, current_user)
    ensure_owner_or_admin(file, current_user)
    status = int(file.file_status)
    if status in (int(FileStatus.PENDING_REVIEW), int(FileStatus.PENDING_APPROVAL)):
        raise AppError(409, "FILE_LOCKED", "审核中的文件禁止更新")
    if status == int(FileStatus.DELETED):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")

    new_name = None
    if file_name is not None:
        new_name = file_name.strip()
        if not new_name or len(new_name) > 255:
            raise validation_error("file_name", "文件名称长度应为 1-255 字")
    new_step = None
    if process_step is not None:
        new_step = process_step.strip()
        if not new_step or len(new_step) > 100:
            raise validation_error("process_step", "工序名称长度应为 1-100 字")
    if remarks is not None and len(remarks) > 1000:
        raise validation_error("remarks", "备注不能超过 1000 字")

    target_code = file.process_code
    if process_code is not None and process_code.strip():
        target_code = normalize_process_code(process_code)
        if status in (int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)):
            if target_code != file.process_code:
                raise AppError(
                    400,
                    "VALIDATION_ERROR",
                    "已批准/已归档文件升版不允许修改工序代码",
                    {"process_code": "升版不允许修改工序代码"},
                )
    target_name = new_name or file.file_name
    target_step = new_step or file.process_step

    target_name_key = build_name_key(target_code, target_name)
    if target_name_key != file.name_key and (
        await file_crud.find_by_name_key(db, target_name_key, exclude_id=file.id)
    ):
        raise AppError(
            409,
            "FILE_NAME_DUPLICATED",
            "同一工序代码下已存在同名文件（忽略大小写/首尾空白）",
        )

    if status in (int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)) and new_file is None:
        raise AppError(400, "NEW_FILE_REQUIRED", "已批准/已归档文件更新必须上传新文件")

    saved = None
    new_version_value: Optional[str] = None
    try:
        if new_file is not None:
            saved = await save_upload_file(new_file)
            new_version_value = next_version(file.version, version_type or "patch")
            if await file_crud.get_version_by_number(db, file.id, new_version_value):
                raise AppError(409, "VERSION_EXISTS", "该版本号已存在")
            await file_crud.add_file_version(
                db,
                file,
                version=new_version_value,
                relative_path=saved["relative_path"],
                file_hash=saved["file_hash"],
                file_size=saved["file_size"],
                uploader_id=current_user.id,
                change_description=change_description,
            )
            file.version = new_version_value
            file.storage_path = saved["relative_path"]
            file.file_size = saved["file_size"]
            file.file_type = saved["file_type"]
            if status in (int(FileStatus.APPROVED), int(FileStatus.ARCHIVED)):
                # 升版后回到草稿，需重新审批
                file.file_status = int(FileStatus.DRAFT)
                file.approved_at = None
                file.archived_at = None
                file.archived_by = None
        file.file_name = target_name
        file.name_key = target_name_key
        file.process_step = target_step
        file.process_code = target_code
        if remarks is not None:
            file.remarks = remarks
        file.last_update_time = utcnow()
        await add_operation_log(
            db,
            operation_type=OperationType.UPDATE,
            target_type="file",
            target_id=file.id,
            file_id=file.id,
            operator_id=current_user.id,
            details=(
                f"更新文件：{file.file_name} {new_version_value or file.version}"
                + (f"；变更说明：{change_description}" if change_description else "")
            ),
            request=request,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if saved is not None:
            remove_stored_file(saved["relative_path"])
        raise AppError(
            409,
            "FILE_NAME_DUPLICATED",
            "同一工序代码下已存在同名文件（忽略大小写/首尾空白）",
        )
    except Exception:
        await db.rollback()
        if saved is not None:
            remove_stored_file(saved["relative_path"])
        raise
    detail = await file_crud.get_file_for_detail(db, file.id)
    return _detail_of(detail, current_user)


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    request: Request,
    current_user: User = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    """软删除文件（状态置 0，审核中禁止）。"""
    file = await _load_visible_file(db, file_id, current_user)
    status = int(file.file_status)
    if status in (int(FileStatus.PENDING_REVIEW), int(FileStatus.PENDING_APPROVAL)):
        raise AppError(409, "FILE_LOCKED", "审核中的文件禁止删除")
    admin = is_admin(current_user)
    owner = file.creator_id == current_user.id or file.uploader_id == current_user.id
    if not admin:
        if not owner:
            raise AppError(403, "FORBIDDEN", "无权执行该操作")
        if status not in (int(FileStatus.DRAFT),):
            raise AppError(403, "FORBIDDEN", "仅本人草稿可由本人删除，其它状态请联系管理员")
    file.file_status = int(FileStatus.DELETED)
    file.name_key = None
    file.deleted_at = utcnow()
    file.deleted_by = current_user.id
    file.current_approver_id = None
    file.last_update_time = utcnow()
    await add_operation_log(
        db,
        operation_type=OperationType.DELETE,
        target_type="file",
        target_id=file.id,
        file_id=file.id,
        operator_id=current_user.id,
        details=f"删除文件：{file.file_name}（编号 {file.file_number}）",
        request=request,
    )
    await db.commit()
    return {"message": "文件已删除", "id": file.id}


# ---------------------------------------------------------------------------
# 下载 / 版本
# ---------------------------------------------------------------------------
async def _download_response(
    db: AsyncSession,
    file: ProcessFile,
    target_version: str,
    request: Request,
    current_user: User,
):
    version_row = await file_crud.get_version_by_number(db, file.id, target_version)
    if version_row is None:
        raise AppError(404, "VERSION_NOT_FOUND", "文件版本不存在")
    path = resolve_storage_path(version_row.file_path)
    if not path.is_file():
        raise AppError(404, "FILE_CONTENT_MISSING", "文件内容缺失，请联系管理员")
    await add_operation_log(
        db,
        operation_type=OperationType.DOWNLOAD,
        target_type="file",
        target_id=file.id,
        file_id=file.id,
        operator_id=current_user.id,
        details=f"下载文件：{file.file_name} {target_version}",
        request=request,
    )
    await db.commit()
    ext = Path(version_row.file_path).suffix or (file.file_type or "")
    headers = {
        "Content-Disposition": build_content_disposition(
            file.file_number, target_version, ext
        ),
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(
        path=str(path),
        media_type=guess_media_type(ext),
        headers=headers,
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    request: Request,
    version: Optional[str] = Query(None, description="指定版本号，缺省当前版本"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """鉴权下载当前或指定版本。"""
    file = await _load_visible_file(db, file_id, current_user)
    target_version = _normalize_download_version(version, file.version)
    return await _download_response(db, file, target_version, request, current_user)


@router.get("/{file_id}/versions")
async def list_file_versions(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """版本历史（按上传时间倒序，纯数组）。"""
    file = await _load_visible_file(db, file_id, current_user)
    versions = await file_crud.get_versions(db, file.id)
    return [version_item(item) for item in versions]


@router.get("/{file_id}/versions/{version}/download")
async def download_file_version(
    file_id: int,
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载指定历史版本。"""
    file = await _load_visible_file(db, file_id, current_user)
    target_version = _normalize_download_version(version, file.version)
    return await _download_response(db, file, target_version, request, current_user)


# ---------------------------------------------------------------------------
# 审批动作
# ---------------------------------------------------------------------------
@router.post("/{file_id}/submit-review")
async def submit_review(
    file_id: int,
    request: Request,
    payload: Optional[SubmitReviewRequest] = None,
    current_user: User = Depends(require_permission("update")),
    db: AsyncSession = Depends(get_db),
):
    """提交审核（文件 1 -> 2，新建审批流程）。"""
    file = await _load_visible_file(db, file_id, current_user)
    ensure_owner_or_admin(file, current_user)
    if int(file.file_status) != int(FileStatus.DRAFT):
        raise AppError(
            409,
            "STATE_CONFLICT",
            f"当前状态为{status_label(int(file.file_status))}，不可提交审核",
        )
    reviewer = await approval_crud.resolve_assignee(
        db,
        payload.reviewer_id if payload else None,
        "review",
        "reviewer_id",
    )
    approver = await approval_crud.resolve_assignee(
        db,
        payload.approver_id if payload else None,
        "approve",
        "approver_id",
    )
    flow = await approval_crud.submit_for_review(
        db,
        file=file,
        initiator=current_user,
        reviewer=reviewer,
        approver=approver,
        comment=payload.comment if payload else None,
        request=request,
    )
    await db.commit()
    return {
        "message": "已提交审核",
        "file_id": file.id,
        "file_status": int(file.file_status),
        "file_status_text": status_label(int(file.file_status)),
        "flow_id": flow.id,
        "version": flow.version,
        "reviewer": user_brief(reviewer),
        "approver": user_brief(approver),
    }


@router.post("/{file_id}/review")
async def review_file_endpoint(
    file_id: int,
    payload: ReviewRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """审核环节（通过 -> 待批准；驳回 -> 草稿）。

    权限按动作分支：pass 需 review，reject 需 reject；且必须是当前步骤审批人。
    """
    if payload.result == "reject":
        if not has_permission(current_user, "reject"):
            raise forbidden_permission("reject")
        if not (payload.comment or "").strip():
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "驳回时必须填写审批意见",
                {"comment": "驳回意见不能为空"},
            )
    elif not has_permission(current_user, "review"):
        raise forbidden_permission("review")
    file = await file_crud.get_file_for_detail(db, file_id)
    if file is None or int(file.file_status) == int(FileStatus.DELETED):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")
    if int(file.file_status) != int(FileStatus.PENDING_REVIEW):
        raise AppError(
            409,
            "STATE_CONFLICT",
            f"当前状态为{status_label(int(file.file_status))}，不可执行审核",
        )
    flow = await file_crud.get_active_flow(db, file.id)
    if flow is None:
        raise AppError(409, "STATE_CONFLICT", "当前没有进行中的审批流程")
    step = next((item for item in flow.steps if item.step_number == 1), None)
    outcome = await approval_crud.review_file(
        db,
        file=file,
        flow=flow,
        step=step,
        current_user=current_user,
        result=payload.result,
        comment=payload.comment,
        request=request,
    )
    await db.commit()
    next_approver = outcome.get("next_approver")
    return {
        "message": outcome["message"],
        "file_id": file.id,
        "file_status": int(file.file_status),
        "file_status_text": status_label(int(file.file_status)),
        "flow_id": flow.id,
        "next_approver": user_brief(next_approver) if next_approver else None,
    }


@router.post("/{file_id}/approve")
async def approve_file_endpoint(
    file_id: int,
    payload: ReviewRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批准环节（通过 -> 已批准；驳回 -> 草稿）。

    权限按动作分支：pass 需 approve，reject 需 reject；且必须是当前步骤审批人。
    """
    if payload.result == "reject":
        if not has_permission(current_user, "reject"):
            raise forbidden_permission("reject")
        if not (payload.comment or "").strip():
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "驳回时必须填写审批意见",
                {"comment": "驳回意见不能为空"},
            )
    elif not has_permission(current_user, "approve"):
        raise forbidden_permission("approve")
    file = await file_crud.get_file_for_detail(db, file_id)
    if file is None or int(file.file_status) == int(FileStatus.DELETED):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")
    if int(file.file_status) != int(FileStatus.PENDING_APPROVAL):
        raise AppError(
            409,
            "STATE_CONFLICT",
            f"当前状态为{status_label(int(file.file_status))}，不可执行批准",
        )
    flow = await file_crud.get_active_flow(db, file.id)
    if flow is None:
        raise AppError(409, "STATE_CONFLICT", "当前没有进行中的审批流程")
    step = next((item for item in flow.steps if item.step_number == 2), None)
    outcome = await approval_crud.approve_file(
        db,
        file=file,
        flow=flow,
        step=step,
        current_user=current_user,
        result=payload.result,
        comment=payload.comment,
        request=request,
    )
    await db.commit()
    return {
        "message": outcome["message"],
        "file_id": file.id,
        "file_status": int(file.file_status),
        "file_status_text": status_label(int(file.file_status)),
        "flow_id": flow.id,
        "next_approver": None,
    }


@router.post("/{file_id}/archive")
async def archive_file_endpoint(
    file_id: int,
    request: Request,
    payload: Optional[ArchiveRequest] = None,
    current_user: User = Depends(require_permission("archive")),
    db: AsyncSession = Depends(get_db),
):
    """归档（文件 4 -> 5，并自动生成清单快照）。"""
    from services.catalog_service import refresh_catalog

    file = await file_crud.get_file_for_detail(db, file_id)
    if file is None or int(file.file_status) == int(FileStatus.DELETED):
        raise AppError(404, "FILE_NOT_FOUND", "文件不存在")
    await approval_crud.archive_file(
        db,
        file=file,
        current_user=current_user,
        comment=payload.comment if payload else None,
        request=request,
    )
    snapshot = await refresh_catalog(
        db, refresh_type="auto", operator_id=None
    )
    await db.commit()
    return {
        "message": "已归档，文件清单已更新",
        "file_id": file.id,
        "file_status": int(file.file_status),
        "file_status_text": status_label(int(file.file_status)),
        "archived_at": iso(file.archived_at),
        "snapshot": snapshot_item(snapshot),
    }


# ---------------------------------------------------------------------------
# 签名 / 流程 / 日志
# ---------------------------------------------------------------------------
@router.get("/{file_id}/signatures")
async def list_signatures(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """签名列表（按签名时间升序，纯数组）。"""
    file = await _load_file_related(db, file_id, current_user)
    signatures = await file_crud.get_signatures(db, file.id)
    return [signature_item(item) for item in signatures]


@router.get("/{file_id}/approval")
async def get_approval(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前/历史审批流程、步骤与签名。"""
    from utils.serializers import flow_detail

    file = await _load_file_related(db, file_id, current_user)
    signatures = await file_crud.get_signatures(db, file.id)
    flows = sorted(file.flows, key=lambda item: item.id)
    current = flows[-1] if flows else None

    def build(flow):
        matched = [item for item in signatures if item.version == flow.version]
        return flow_detail(flow, matched)

    return {
        "file_id": file.id,
        "current_flow": build(current) if current is not None else None,
        "history": [build(item) for item in reversed(flows[:-1])],
    }


@router.get("/{file_id}/logs")
async def list_file_logs_endpoint(
    file_id: int,
    page: int = Query(1),
    size: int = Query(10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单文件操作日志（分页）。"""
    file = await _load_file_related(db, file_id, current_user)
    page, size = normalize_page(page, size)
    logs, total = await file_crud.list_file_logs(db, file.id, page=page, size=size)
    return page_result([log_item(item) for item in logs], total, page, size)
