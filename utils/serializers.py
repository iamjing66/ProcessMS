"""统一响应序列化：严格对齐 docs/API.md 的字段结构。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.approval import ApprovalFlow, ApprovalStep, FileSignature
from models.catalog import CatalogItem, CatalogSnapshot
from models.enums import (
    ROLE_DISPLAY_NAMES,
    catalog_update_way_label,
    flow_status_label,
    operation_label,
    status_label,
    step_status_label,
)
from models.file import FileOperationLog, FileVersion, ProcessFile
from models.user import Permission, Role, User
from utils.time import format_cn, iso


def _role_display(user: Optional[User]) -> str:
    if user is None:
        return ""
    for link in user.roles:
        if link.role is not None and link.role.name in ROLE_DISPLAY_NAMES:
            return ROLE_DISPLAY_NAMES[link.role.name]
    return ""


def user_brief(user: Optional[User]) -> Optional[Dict[str, Any]]:
    """UserBrief 数据字典结构。"""
    if user is None:
        return None
    return {
        "id": user.id,
        "employee_id": user.employee_id,
        "username": user.username,
        "real_name": user.real_name,
        "department": user.department,
        "position": user.position,
    }


def role_item(role: Role) -> Dict[str, Any]:
    return {"id": role.id, "name": role.name, "description": role.description}


def permission_item(permission: Permission) -> Dict[str, Any]:
    return {
        "id": permission.id,
        "code": permission.code,
        "name": permission.name,
        "description": permission.description,
    }


def user_item(user: User) -> Dict[str, Any]:
    data = user_brief(user) or {}
    data.update(
        {
            "is_active": bool(user.is_active),
            "roles": [role_item(link.role) for link in user.roles if link.role is not None],
            "last_login": iso(user.last_login),
            "created_at": iso(user.created_at),
        }
    )
    return data


def file_item(file: ProcessFile) -> Dict[str, Any]:
    """FileItem 列表元素结构。"""
    return {
        "id": file.id,
        "file_number": file.file_number,
        "file_name": file.file_name,
        "file_type": file.file_type,
        "process_code": file.process_code,
        "process_step": file.process_step,
        "version": file.version,
        "file_status": int(file.file_status),
        "file_status_text": status_label(int(file.file_status)),
        "creator": user_brief(file.creator),
        "uploader": user_brief(file.uploader),
        "initial_upload_time": iso(file.initial_upload_time),
        "last_update_time": iso(file.last_update_time),
        "file_size": file.file_size,
        "current_approver": user_brief(file.current_approver),
        "remarks": file.remarks,
    }


def version_item(version: FileVersion) -> Dict[str, Any]:
    return {
        "id": version.id,
        "file_id": version.file_id,
        "version": version.version,
        "file_size": version.file_size,
        "file_hash": version.file_hash,
        "change_description": version.change_description,
        "uploader": user_brief(version.uploader),
        "upload_time": iso(version.upload_time),
        "download_url": f"/api/files/{version.file_id}/download?version={version.version}",
    }


def signature_item(signature: FileSignature) -> Dict[str, Any]:
    signer = signature.signer
    role_cn = _role_display(signer)
    action = "审核" if signature.step_type == "review" else "批准"
    result = "通过" if (signature.result or "pass") == "pass" else "驳回"
    signature_text = (
        f"{signature.signer_name}（{role_cn}）于 {format_cn(signature.signed_at)} "
        f"{action}{result}"
        if role_cn
        else f"{signature.signer_name}于 {format_cn(signature.signed_at)} {action}{result}"
    )
    return {
        "id": signature.id,
        "file_id": signature.file_id,
        "version": signature.version,
        "step_type": signature.step_type,
        "step_name": signature.step_name,
        "signer": user_brief(signer),
        "signer_name": signature.signer_name,
        "signature_text": signature_text,
        "signed_at": iso(signature.signed_at),
        "remark": signature.remark,
    }


def step_item(step: ApprovalStep) -> Dict[str, Any]:
    return {
        "step_number": step.step_number,
        "step_name": step.step_name,
        "approver": user_brief(step.approver),
        "approval_status": int(step.approval_status),
        "approval_status_text": step_status_label(int(step.approval_status)),
        "approval_time": iso(step.approval_time),
        "approval_comment": step.approval_comment,
    }


def flow_detail(
    flow: ApprovalFlow, signatures: Optional[List[FileSignature]] = None
) -> Dict[str, Any]:
    return {
        "id": flow.id,
        "file_id": flow.file_id,
        "version": flow.version,
        "flow_type": flow.flow_type,
        "current_step": flow.current_step,
        "status": int(flow.status),
        "status_text": flow_status_label(int(flow.status)),
        "initiator": user_brief(flow.initiator),
        "created_at": iso(flow.created_at),
        "completed_at": iso(flow.completed_at),
        "reject_reason": flow.reject_reason,
        "steps": [step_item(step) for step in flow.steps],
        "signatures": [signature_item(item) for item in (signatures or [])],
    }


def flow_summary(flow: ApprovalFlow) -> Dict[str, Any]:
    file = flow.file
    return {
        "id": flow.id,
        "file_id": flow.file_id,
        "file_number": file.file_number if file else None,
        "file_name": file.file_name if file else None,
        "version": flow.version,
        "current_step": flow.current_step,
        "status": int(flow.status),
        "status_text": flow_status_label(int(flow.status)),
        "initiator": user_brief(flow.initiator),
        "created_at": iso(flow.created_at),
        "completed_at": iso(flow.completed_at),
    }


def approval_summary(flow: Optional[ApprovalFlow]) -> Optional[Dict[str, Any]]:
    """FileDetail.approval 摘要。"""
    if flow is None:
        return None
    current_step = None
    for step in flow.steps:
        if step.step_number == flow.current_step:
            current_step = step
            break
    current_approver = None
    if flow.status == 1:
        current_approver = user_brief(current_step.approver) if current_step else None
    return {
        "flow_id": flow.id,
        "status": int(flow.status),
        "status_text": flow_status_label(int(flow.status)),
        "current_step": flow.current_step,
        "current_step_name": current_step.step_name if current_step else None,
        "current_approver": current_approver,
    }


def file_detail(
    file: ProcessFile,
    allowed_actions: Optional[List[str]] = None,
    can_download: bool = True,
) -> Dict[str, Any]:
    """FileDetail 结构 = FileItem + 详情扩展字段。"""
    data = file_item(file)
    versions = list(file.versions or [])
    latest = versions[0] if versions else None
    flows = list(file.flows or [])
    latest_flow = flows[-1] if flows else None
    data.update(
        {
            "version_count": len(versions),
            "latest_version": (
                {
                    "version": latest.version,
                    "upload_time": iso(latest.upload_time),
                    "change_description": latest.change_description,
                }
                if latest is not None
                else None
            ),
            "approval": approval_summary(latest_flow),
            "signatures": [signature_item(item) for item in (file.signatures or [])],
            "allowed_actions": allowed_actions or [],
            "can_download": bool(can_download),
        }
    )
    return data


def snapshot_item(snapshot: CatalogSnapshot) -> Dict[str, Any]:
    return {
        "id": snapshot.id,
        "snapshot_no": snapshot.snapshot_no,
        "refresh_type": snapshot.refresh_type,
        "refresh_type_text": catalog_update_way_label(snapshot.refresh_type),
        "operator": user_brief(snapshot.operator),
        "item_count": snapshot.item_count,
        "created_at": iso(snapshot.created_at),
    }


def catalog_item(item: CatalogItem, approved_at=None) -> Dict[str, Any]:
    """CatalogItem：approved_at 由 process_files 派生（此处由调用方传入）。"""
    return {
        "id": item.id,
        "snapshot_id": item.snapshot_id,
        "file_id": item.file_id,
        "file_number": item.file_number,
        "file_name": item.file_name,
        "version": item.version,
        "process_code": item.process_code,
        "process_step": item.process_step,
        "creator_id": item.creator_id,
        "creator_name": item.creator_name,
        "file_size": item.file_size,
        "approved_at": iso(approved_at),
        "file_status": int(item.file_status),
        "file_status_text": status_label(int(item.file_status)),
        "download_url": f"/api/files/{item.file_id}/download?version={item.version}",
    }


def log_item(log: FileOperationLog) -> Dict[str, Any]:
    return {
        "id": log.id,
        "file_id": log.file_id,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "operator": user_brief(log.operator),
        "operation_type": log.operation_type,
        "operation_type_text": operation_label(log.operation_type),
        "operation_time": iso(log.operation_time),
        "operation_details": log.operation_details,
        "ip_address": log.ip_address,
    }


def pending_item(flow: ApprovalFlow, step: ApprovalStep, file: ProcessFile) -> Dict[str, Any]:
    return {
        "file": file_item(file),
        "flow_id": flow.id,
        "step_number": step.step_number,
        "step_name": step.step_name,
        "approval_status": int(step.approval_status),
        "submitted_at": iso(flow.created_at),
        "initiator": user_brief(flow.initiator),
    }
