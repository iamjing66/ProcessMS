# -*- coding: utf-8 -*-
"""测试辅助函数：统一断言、登录、上传、审批动作封装。

约定：
- 所有请求路径带 /api 前缀（API.md v1.0）；
- 上传/更新为 multipart/form-data，其余为 JSON；
- 错误断言统一走 assert_error，校验 {code,message,detail} 结构。
"""
from __future__ import annotations

from typing import Any, Optional

from httpx import AsyncClient, Response

FILE_STATUS_TEXT = {
    0: "已删除",
    1: "草稿",
    2: "待审核",
    3: "待批准",
    4: "已批准",
    5: "已归档",
}

# 默认测试文件内容（PDF 文件头，避免某些实现按内容嗅探类型）
DEFAULT_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def assert_error(resp: Response, status: int, code: Optional[str] = None) -> dict:
    """断言统一错误结构 {code, message, detail}。"""
    assert resp.status_code == status, (
        f"期望 HTTP {status}，实际 {resp.status_code}，响应={resp.text[:500]}"
    )
    body = resp.json()
    assert isinstance(body, dict), f"错误响应应为 JSON 对象，实际={body!r}"
    assert "code" in body, f"错误响应缺少 code: {body}"
    assert "message" in body, f"错误响应缺少 message: {body}"
    assert isinstance(body["message"], str) and body["message"], "message 必须为非空字符串（中文提示）"
    assert "detail" in body, f"错误响应缺少 detail: {body}"
    if code is not None:
        assert body["code"] == code, f"期望错误码 {code}，实际 {body['code']}（{body['message']}）"
    return body


def assert_ok(resp: Response, status: int = 200) -> dict:
    assert resp.status_code == status, (
        f"期望 HTTP {status}，实际 {resp.status_code}，响应={resp.text[:500]}"
    )
    return resp.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def login(client: AsyncClient, username: str, password: str) -> Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


async def login_token(client: AsyncClient, username: str, password: str) -> str:
    resp = await login(client, username, password)
    assert_ok(resp, 200)
    body = resp.json()
    assert "access_token" in body and body["access_token"]
    return body["access_token"]


async def upload_file(
    client: AsyncClient,
    headers: dict,
    *,
    filename: str = "sample.pdf",
    content: bytes = DEFAULT_PDF,
    file_name: str = "主轴加工工艺",
    process_step: str = "车削",
    process_code: Optional[str] = "CN",
    version: Optional[str] = None,
    remarks: Optional[str] = None,
    expect_status: int = 201,
) -> Any:
    """上传工艺文件；默认断言 201 并返回 FileDetail。"""
    data: dict[str, str] = {"file_name": file_name, "process_step": process_step}
    if process_code is not None:
        data["process_code"] = process_code
    if version is not None:
        data["version"] = version
    if remarks is not None:
        data["remarks"] = remarks
    resp = await client.post(
        "/api/files/upload",
        headers=headers,
        data=data,
        files={"file": (filename, content, "application/pdf")},
    )
    assert_ok(resp, expect_status)
    return resp.json()


async def get_file(client: AsyncClient, headers: dict, file_id: int, expect_status: int = 200) -> Any:
    resp = await client.get(f"/api/files/{file_id}", headers=headers)
    return assert_ok(resp, expect_status)


async def submit_review(client: AsyncClient, headers: dict, file_id: int, **payload) -> dict:
    resp = await client.post(f"/api/files/{file_id}/submit-review", headers=headers, json=payload or {})
    return assert_ok(resp, 200)


async def review(client: AsyncClient, headers: dict, file_id: int, result: str = "pass", comment: str = "工艺参数无误") -> dict:
    resp = await client.post(
        f"/api/files/{file_id}/review", headers=headers, json={"result": result, "comment": comment}
    )
    return assert_ok(resp, 200)


async def approve(client: AsyncClient, headers: dict, file_id: int, result: str = "pass", comment: str = "同意") -> dict:
    resp = await client.post(
        f"/api/files/{file_id}/approve", headers=headers, json={"result": result, "comment": comment}
    )
    return assert_ok(resp, 200)


async def archive(client: AsyncClient, headers: dict, file_id: int, comment: str = "资料室归档") -> dict:
    resp = await client.post(f"/api/files/{file_id}/archive", headers=headers, json={"comment": comment})
    return assert_ok(resp, 200)


async def upload_and_submit(
    client: AsyncClient,
    tokens: dict,
    *,
    uploader: str = "engineer01",
    submit_payload: Optional[dict] = None,
    **upload_kwargs,
) -> dict:
    """上传并提交审核，返回文件详情（状态 2）。"""
    detail = await upload_file(client, tokens[uploader], **upload_kwargs)
    file_id = detail["id"]
    result = await submit_review(client, tokens[uploader], file_id, **(submit_payload or {}))
    assert result["file_status"] == 2
    return await get_file(client, tokens[uploader], file_id)


async def complete_flow(
    client: AsyncClient,
    tokens: dict,
    *,
    uploader: str = "engineer01",
    reviewer: str = "leader01",
    approver: str = "manager01",
    archivist: str = "archivist01",
    review_result: str = "pass",
    approve_result: str = "pass",
    do_archive: bool = True,
    submit_payload: Optional[dict] = None,
    reviewer_id: Optional[int] = None,
    approver_id: Optional[int] = None,
    **upload_kwargs,
) -> dict:
    """跑完整流程：上传→提交→审核→批准（→归档），返回 {"file": FileDetail, ...动作响应}。

    注意：提交时显式指定 reviewer_id/approver_id，避免自动分配（admin 也具备审批权限，
    自动分配会落到最早创建的 admin 上，导致审批人断言不稳定）。
    """
    detail = await upload_file(client, tokens[uploader], **upload_kwargs)
    file_id = detail["id"]
    payload = dict(submit_payload or {})
    if reviewer_id is not None:
        payload["reviewer_id"] = reviewer_id
    if approver_id is not None:
        payload["approver_id"] = approver_id
    submitted = await submit_review(client, tokens[uploader], file_id, **payload)
    reviewed = await review(client, tokens[reviewer], file_id, result=review_result)
    approved = None
    archived = None
    if review_result == "pass":
        approved = await approve(client, tokens[approver], file_id, result=approve_result)
        if approve_result == "pass" and do_archive:
            archived = await archive(client, tokens[archivist], file_id)
    final = await get_file(
        client,
        tokens["admin"] if review_result != "pass" else tokens[uploader],
        file_id,
    )
    return {
        "file": final,
        "file_id": file_id,
        "uploaded": detail,
        "submitted": submitted,
        "reviewed": reviewed,
        "approved": approved,
        "archived": archived,
    }

async def update_file(
    client: AsyncClient,
    headers: dict,
    file_id: int,
    *,
    new_file: bool = False,
    filename: str = "v2.pdf",
    content: bytes = DEFAULT_PDF,
    expect_status: int = 200,
    **data,
) -> Any:
    """更新文件（可选上传新版本文件 new_file）。"""
    if new_file:
        resp = await client.put(
            f"/api/files/{file_id}",
            headers=headers,
            data=data,
            files={"new_file": (filename, content, "application/pdf")},
        )
    else:
        resp = await client.put(f"/api/files/{file_id}", headers=headers, data=data or None)
    return assert_ok(resp, expect_status)


async def download(client: AsyncClient, headers: dict, file_id: int, version: Optional[str] = None, expect_status: int = 200):
    """下载文件内容（可选指定版本）。"""
    params = {"version": version} if version else None
    resp = await client.get(f"/api/files/{file_id}/download", headers=headers, params=params)
    assert resp.status_code == expect_status, (
        f"期望下载 HTTP {expect_status}，实际 {resp.status_code}，响应={resp.text[:300]}"
    )
    return resp


async def get_versions(client: AsyncClient, headers: dict, file_id: int) -> list:
    resp = await client.get(f"/api/files/{file_id}/versions", headers=headers)
    body = assert_ok(resp, 200)
    assert isinstance(body, list), f"版本列表应为数组，实际={type(body)}"
    return body


async def get_signatures(client: AsyncClient, headers: dict, file_id: int) -> list:
    resp = await client.get(f"/api/files/{file_id}/signatures", headers=headers)
    body = assert_ok(resp, 200)
    assert isinstance(body, list), f"签名列表应为数组，实际={type(body)}"
    return body


async def get_approval(client: AsyncClient, headers: dict, file_id: int) -> dict:
    resp = await client.get(f"/api/files/{file_id}/approval", headers=headers)
    return assert_ok(resp, 200)


async def get_file_logs(client: AsyncClient, headers: dict, file_id: int, page: int = 1, size: int = 100) -> dict:
    resp = await client.get(f"/api/files/{file_id}/logs?page={page}&size={size}", headers=headers)
    return assert_ok(resp, 200)
