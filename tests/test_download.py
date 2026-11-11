# -*- coding: utf-8 -*-
"""下载用例：鉴权、可见性、版本、路径穿越、内容缺失。"""
from __future__ import annotations

from pathlib import Path

from tests.helpers import DEFAULT_PDF, assert_error, assert_ok, download, get_file_logs, upload_file


async def test_download_success_headers_and_content(client, headers):
    content = b"%PDF-1.4\nDOWNLOAD-CONTENT\n"
    detail = await upload_file(client, headers["engineer01"], file_name="下载测试", content=content)
    resp = await download(client, headers["engineer01"], detail["id"])

    assert resp.content == content
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition.lower()
    assert detail["file_number"] in disposition
    assert resp.headers.get("x-content-type-options", "").lower() == "nosniff"
    assert resp.headers.get("content-type", "").startswith("application/pdf")


async def test_download_requires_token(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="下载需登录")
    resp = await client.get(f"/api/files/{detail['id']}/download")
    assert_error(resp, 401, "AUTH_REQUIRED")


async def test_download_missing_file(client, headers):
    resp = await client.get("/api/files/999999/download", headers=headers["admin"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_download_other_users_draft_hidden(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="他人草稿下载")
    resp = await client.get(f"/api/files/{detail['id']}/download", headers=headers["engineer02"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_download_deleted_file(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="删除后下载")
    assert_ok(await client.delete(f"/api/files/{detail['id']}", headers=headers["engineer01"]), 200)
    resp = await client.get(f"/api/files/{detail['id']}/download", headers=headers["engineer01"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_download_archived_visible_to_all_logged_users(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    assert_ok(await client.get(f"/api/files/{file_id}", headers=headers["norole01"]), 200)
    resp = await download(client, headers["norole01"], file_id)
    assert resp.content == DEFAULT_PDF


async def test_download_content_missing_on_disk(client, headers, db_session):
    from sqlalchemy import select

    from models.file import ProcessFile
    from tests.conftest import get_settings

    detail = await upload_file(client, headers["engineer01"], file_name="磁盘文件丢失")
    row = (await db_session.execute(select(ProcessFile).where(ProcessFile.id == detail["id"]))).scalar_one()

    candidates = [Path(row.storage_path)]
    if not Path(row.storage_path).is_absolute():
        candidates.append(Path(get_settings().UPLOAD_DIR) / row.storage_path)
        candidates.append(Path(get_settings().UPLOAD_DIR) / Path(row.storage_path).name)
    removed = False
    for candidate in candidates:
        if candidate.exists():
            candidate.unlink()
            removed = True
            break
    assert removed, f"未找到落盘文件以模拟丢失，候选={candidates}"

    resp = await client.get(f"/api/files/{detail['id']}/download", headers=headers["engineer01"])
    assert_error(resp, 404, "FILE_CONTENT_MISSING")


async def test_download_path_traversal_version_rejected(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="路径穿越")
    for bad_version in ["../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "V1.0.0/../../secret"]:
        resp = await client.get(
            f"/api/files/{detail['id']}/download",
            headers=headers["engineer01"],
            params={"version": bad_version},
        )
        assert resp.status_code in (400, 404), f"路径穿越版本应被拒绝：{bad_version} -> {resp.status_code}"
        body = resp.json()
        assert body.get("code") in {"VERSION_NOT_FOUND", "VALIDATION_ERROR", "VERSION_FORMAT_INVALID"}


async def test_download_logs_recorded(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="下载日志")
    await download(client, headers["engineer01"], detail["id"])
    logs = await get_file_logs(client, headers["engineer01"], detail["id"])
    assert any(item["operation_type"] == "download" for item in logs["items"])
