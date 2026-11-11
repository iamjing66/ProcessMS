# -*- coding: utf-8 -*-
"""分页默认值与统一分页信封（API v1.0.3：默认 size=10）。"""
from __future__ import annotations

from tests.helpers import assert_ok


async def test_default_page_size_is_10(client, headers):
    """文件/清单/日志/待办/用户列表默认 size=10。"""
    files = assert_ok(await client.get("/api/files", headers=headers["admin"]), 200)
    assert files["size"] == 10 and files["page"] == 1

    catalogs = assert_ok(await client.get("/api/catalogs", headers=headers["admin"]), 200)
    assert catalogs["size"] == 10

    logs = assert_ok(await client.get("/api/logs", headers=headers["admin"]), 200)
    assert logs["size"] == 10

    pending = assert_ok(await client.get("/api/approvals/pending", headers=headers["leader01"]), 200)
    assert pending["size"] == 10

    users = assert_ok(await client.get("/api/users", headers=headers["admin"]), 200)
    assert users["size"] == 10


async def test_file_logs_default_page_size_is_10(client, headers):
    from tests.helpers import get_file_logs, upload_file

    detail = await upload_file(client, headers["engineer01"], file_name="日志分页默认值")
    body = await get_file_logs(client, headers["engineer01"], detail["id"])
    # get_file_logs 显式传 page/size=100，这里单独验证默认值
    resp = await client.get(f"/api/files/{detail['id']}/logs", headers=headers["engineer01"])
    body = assert_ok(resp, 200)
    assert body["size"] == 10
    assert body["page"] == 1
