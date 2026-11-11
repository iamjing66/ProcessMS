# -*- coding: utf-8 -*-
"""软删除用例：不可见、权限、编号不复用、审核中禁止。"""
from __future__ import annotations

import asyncio

from tests.helpers import assert_error, assert_ok, upload_file


async def test_owner_delete_draft_and_invisible(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="待删除草稿")
    file_id = detail["id"]

    resp = await client.delete(f"/api/files/{file_id}", headers=headers["engineer01"])
    body = assert_ok(resp, 200)
    assert body["id"] == file_id
    assert body.get("message")

    assert_error(await client.get(f"/api/files/{file_id}", headers=headers["engineer01"]), 404, "FILE_NOT_FOUND")
    listing = assert_ok(await client.get("/api/files?page=1&size=100", headers=headers["admin"]), 200)
    assert all(item["id"] != file_id for item in listing["items"])


async def test_delete_requires_permission_or_ownership(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="越权删除")

    # 其他工程师看不到草稿：按可见性规则统一 404（API.md §0.7）
    resp = await client.delete(f"/api/files/{detail['id']}", headers=headers["engineer02"])
    assert_error(resp, 404, "FILE_NOT_FOUND")

    # 无 delete 权限：依赖先于资源校验，返回 403
    resp = await client.delete(f"/api/files/{detail['id']}", headers=headers["manager01"])
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_admin_can_delete_others_draft(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="管理员删除")
    assert_ok(await client.delete(f"/api/files/{detail['id']}", headers=headers["admin"]), 200)
    assert_error(await client.get(f"/api/files/{detail['id']}", headers=headers["admin"]), 404, "FILE_NOT_FOUND")


async def test_delete_locked_during_review(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.delete(f"/api/files/{detail['id']}", headers=headers["engineer01"])
    assert_error(resp, 409, "FILE_LOCKED")


async def test_delete_archived_file(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]

    # 契约 §6.2 #10：已归档文件只有 admin 可软删，本人不能删
    assert_error(await client.delete(f"/api/files/{file_id}", headers=headers["engineer01"]), 403)
    assert_ok(await client.delete(f"/api/files/{file_id}", headers=headers["admin"]), 200)
    assert_error(await client.get(f"/api/files/{file_id}", headers=headers["engineer01"]), 404, "FILE_NOT_FOUND")

    # 归档文件被删除后，清单刷新不再包含（跨秒避免复用归档时的同秒快照）
    await asyncio.sleep(1.05)
    refresh = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    snapshot_id = refresh["snapshot"]["id"]
    catalog = assert_ok(
        await client.get(f"/api/catalogs?snapshot_id={snapshot_id}&page=1&size=100", headers=headers["admin"]),
        200,
    )
    assert all(item["file_id"] != file_id for item in catalog["items"])


async def test_delete_nonexistent(client, headers):
    resp = await client.delete("/api/files/999999", headers=headers["admin"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_deleted_number_not_reused(client, headers):
    """软删后同工序同名可重建，但编号不重复。"""
    first = await upload_file(client, headers["engineer01"], file_name="编号不复用", process_code="BR")
    assert_ok(await client.delete(f"/api/files/{first['id']}", headers=headers["engineer01"]), 200)
    second = await upload_file(client, headers["engineer02"], file_name="编号不复用", process_code="BR")
    assert second["file_number"] != first["file_number"]
    # 删除态编号仍被占用，新编号应递增
    assert int(second["file_number"].split("-")[-1]) > int(first["file_number"].split("-")[-1])
