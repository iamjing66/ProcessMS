# -*- coding: utf-8 -*-
"""文件清单用例：快照生成、手动刷新、历史快照、条目下载链接、每日调度函数。"""
from __future__ import annotations

import asyncio

from tests.helpers import assert_error, assert_ok, download, review


async def test_catalog_empty_before_any_refresh(client, headers):
    body = assert_ok(await client.get("/api/catalogs", headers=headers["admin"]), 200)
    assert body["snapshot"] is None
    assert body["items"] == []
    assert body["total"] == 0


async def test_archive_triggers_auto_catalog(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    file_number = result["file"]["file_number"]

    archived = result["archived"]
    assert archived["snapshot"]["refresh_type"] == "auto"

    body = assert_ok(await client.get("/api/catalogs?page=1&size=20", headers=headers["admin"]), 200)
    snapshot = body["snapshot"]
    assert snapshot is not None
    assert snapshot["refresh_type"] == "auto"
    assert snapshot["refresh_type_text"] == "自动"
    assert snapshot["item_count"] >= 1

    item = next(item for item in body["items"] if item["file_number"] == file_number)
    for field in [
        "id", "snapshot_id", "file_id", "file_number", "file_name", "version",
        "process_code", "process_step", "creator_id", "creator_name",
        "file_size", "approved_at", "file_status", "file_status_text", "download_url",
    ]:
        assert field in item, f"清单条目缺少字段 {field}: {item}"
    assert item["file_id"] == file_id
    assert item["file_status"] == 5
    assert item["file_status_text"] == "已归档"
    assert item["download_url"] == f"/api/files/{file_id}/download?version={item['version']}"

    # 清单条目下载链接可打开
    resp = await download(client, headers["admin"], item["file_id"], version=item["version"])
    assert resp.status_code == 200


async def test_manual_refresh_and_snapshot_contract(client, headers, seed, flow):
    await flow.complete(uploader="engineer01", file_name="清单刷新甲")
    await flow.complete(uploader="engineer02", file_name="清单刷新乙")
    await asyncio.sleep(1.05)  # 跨秒，避免复用归档触发的同秒快照

    resp = await client.post("/api/catalogs/refresh", headers=headers["archivist01"], json={})
    body = assert_ok(resp, 200)
    assert body["message"]
    snapshot = body["snapshot"]
    assert snapshot["refresh_type"] == "manual"
    assert snapshot["refresh_type_text"] == "手动"
    assert snapshot["item_count"] == 2
    assert snapshot["operator"]["id"] == seed["user_ids"]["archivist01"]
    assert snapshot["snapshot_no"].startswith("QD-")

    latest = assert_ok(await client.get("/api/catalogs?page=1&size=20", headers=headers["admin"]), 200)
    assert latest["snapshot"]["id"] == snapshot["id"]
    assert latest["total"] == 2
    numbers = {item["file_number"] for item in latest["items"]}
    assert len(numbers) == 2


async def test_manual_refresh_requires_catalog_manage(client, headers):
    for username in ["engineer01", "leader01", "manager01"]:
        resp = await client.post("/api/catalogs/refresh", headers=headers[username], json={})
        assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_refresh_is_idempotent_within_second(client, headers, flow):
    await flow.complete(uploader="engineer01")
    first = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    second = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    # 同一秒内复用快照；若刚好跨秒则允许出现两个快照，但条目数必须一致
    assert first["snapshot"]["item_count"] == second["snapshot"]["item_count"]
    if first["snapshot"]["snapshot_no"] == second["snapshot"]["snapshot_no"]:
        assert first["snapshot"]["id"] == second["snapshot"]["id"]


async def test_catalog_snapshots_history_and_detail(client, headers, flow):
    await flow.complete(uploader="engineer01")
    await asyncio.sleep(1.05)  # 跨秒，确保手动刷新生成独立 manual 快照
    refresh = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    snapshot_id = refresh["snapshot"]["id"]

    listing = assert_ok(await client.get("/api/catalogs/snapshots?page=1&size=10", headers=headers["admin"]), 200)
    assert listing["total"] >= 2  # 归档自动 + 手动
    assert {"items", "total", "page", "size", "pages"} <= set(listing.keys())

    manual = assert_ok(
        await client.get("/api/catalogs/snapshots?refresh_type=manual&page=1&size=10", headers=headers["admin"]),
        200,
    )
    assert manual["total"] >= 1
    assert all(item["refresh_type"] == "manual" for item in manual["items"])

    detail = assert_ok(
        await client.get(f"/api/catalogs/snapshots/{snapshot_id}", headers=headers["admin"]), 200
    )
    assert detail["snapshot"]["id"] == snapshot_id
    assert isinstance(detail["items"], list)
    assert all(item["snapshot_id"] == snapshot_id for item in detail["items"])


async def test_catalog_not_found(client, headers):
    resp = await client.get("/api/catalogs/snapshots/999999", headers=headers["admin"])
    assert_error(resp, 404, "CATALOG_NOT_FOUND")


async def test_catalog_filter_and_pagination(client, headers, flow):
    await flow.complete(uploader="engineer01", file_name="清单筛选甲")
    await flow.complete(uploader="engineer02", file_name="清单筛选乙")
    await client.post("/api/catalogs/refresh", headers=headers["archivist01"])

    body = assert_ok(await client.get("/api/catalogs?keyword=清单筛选甲&page=1&size=20", headers=headers["admin"]), 200)
    assert body["total"] == 1
    assert body["items"][0]["file_name"] == "清单筛选甲"

    paged = assert_ok(await client.get("/api/catalogs?page=1&size=1", headers=headers["admin"]), 200)
    assert paged["total"] == 2
    assert paged["pages"] == 2
    assert len(paged["items"]) == 1


async def test_catalog_includes_approved_before_archive(client, headers, flow):
    """已批准（4）尚未归档的文件也应进入清单。"""
    detail = await flow.submit(uploader="engineer01")
    await client.post(
        f"/api/files/{detail['id']}/review", headers=headers["leader01"], json={"result": "pass", "comment": "通过"}
    )
    await client.post(
        f"/api/files/{detail['id']}/approve", headers=headers["manager01"], json={"result": "pass", "comment": "同意"}
    )
    refresh = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    assert refresh["snapshot"]["item_count"] == 1
    body = assert_ok(await client.get("/api/catalogs?page=1&size=20", headers=headers["admin"]), 200)
    assert body["items"][0]["file_status"] == 4
    assert body["items"][0]["file_id"] == detail["id"]



async def test_manual_refresh_after_archive_not_reused(client, headers, flow):
    """v1.0.3：快照复用仅限相同刷新方式+操作人，manual 不得复用 auto 快照。"""
    await flow.complete(uploader="engineer01")
    resp = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    assert resp["snapshot"]["refresh_type"] == "manual"
    assert resp["snapshot"]["operator"]["id"] is not None


async def test_catalog_approved_at_semantics(client, headers, flow):
    """CatalogItem.approved_at 来自 process_files.approved_at：状态 4/5 均非空。"""
    # 状态 4（已批准未归档）
    detail = await flow.submit(uploader="engineer01")
    await client.post(
        f"/api/files/{detail['id']}/review", headers=headers["leader01"], json={"result": "pass", "comment": "通过"}
    )
    await client.post(
        f"/api/files/{detail['id']}/approve", headers=headers["manager01"], json={"result": "pass", "comment": "同意"}
    )
    refresh = assert_ok(await client.post("/api/catalogs/refresh", headers=headers["archivist01"]), 200)
    assert refresh["snapshot"]["item_count"] == 1
    body = assert_ok(await client.get("/api/catalogs?page=1&size=20", headers=headers["admin"]), 200)
    item = body["items"][0]
    assert item["file_status"] == 4
    assert item["approved_at"] is not None, "已批准（状态4）文件的清单 approved_at 不应为空"
