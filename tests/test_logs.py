# -*- coding: utf-8 -*-
"""操作日志用例：全量日志筛选分页、文件日志、登录日志。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.conftest import DEMO_PASSWORDS
from tests.helpers import assert_error, assert_ok, get_file_logs, login


async def test_admin_logs_after_flow(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]

    body = assert_ok(await client.get(f"/api/logs?file_id={file_id}&page=1&size=50", headers=headers["admin"]), 200)
    assert body["total"] >= 5
    types = {item["operation_type"] for item in body["items"]}
    assert {"upload", "submit_review", "review_pass", "approve_pass", "archive"} <= types
    item = body["items"][0]
    for field in [
        "id", "file_id", "target_type", "target_id", "operator", "operation_type",
        "operation_type_text", "operation_time", "operation_details",
    ]:
        assert field in item, f"日志项缺少字段 {field}: {item}"
    assert item["operation_type_text"]
    assert item["target_type"] == "file"


async def test_logs_filters(client, headers, flow):
    await flow.complete(uploader="engineer01")

    body = assert_ok(await client.get("/api/logs?operation_type=upload,archive&page=1&size=50", headers=headers["admin"]), 200)
    assert body["total"] >= 2
    assert all(item["operation_type"] in {"upload", "archive"} for item in body["items"])

    body = assert_ok(
        await client.get("/api/logs?target_type=file&operation_type=archive&page=1&size=50", headers=headers["admin"]),
        200,
    )
    assert body["total"] >= 1

    body = assert_ok(await client.get("/api/logs?page=1&size=2", headers=headers["admin"]), 200)
    assert body["size"] == 2
    assert len(body["items"]) <= 2
    assert body["pages"] == (body["total"] + 1) // 2


async def test_login_operation_logged(client, headers):
    resp = await login(client, "engineer01", DEMO_PASSWORDS["engineer01"])
    assert_ok(resp, 200)

    body = assert_ok(await client.get("/api/logs?target_type=auth&page=1&size=50", headers=headers["admin"]), 200)
    assert any(item["operation_type"] == "login" for item in body["items"])


async def test_file_logs_permission(client, headers, seed):
    from tests.helpers import upload_file

    detail = await upload_file(client, headers["engineer01"], file_name="文件日志权限")

    await get_file_logs(client, headers["engineer01"], detail["id"])
    await get_file_logs(client, headers["admin"], detail["id"])

    resp = await client.get(f"/api/files/{detail['id']}/logs", headers=headers["engineer02"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_engineer_cannot_read_full_logs(client, headers):
    resp = await client.get("/api/logs", headers=headers["engineer01"])
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_logs_date_filter_business_day(client, headers, flow):
    """日志 date_start/date_end 按业务时区（Asia/Shanghai）解释。"""
    await flow.complete(uploader="engineer01")
    business_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    body = assert_ok(
        await client.get(
            f"/api/logs?date_start={business_date}&date_end={business_date}&page=1&size=50",
            headers=headers["admin"],
        ),
        200,
    )
    assert body["total"] >= 1
    assert all(item["operation_time"] for item in body["items"])
