# -*- coding: utf-8 -*-
"""统计概览用例。"""
from __future__ import annotations

from tests.helpers import assert_ok, review


async def test_stats_empty_system(client, headers):
    body = assert_ok(await client.get("/api/stats/overview", headers=headers["admin"]), 200)
    assert body["files"]["total"] == 0
    assert body["files"]["by_status"] == {
        "draft": 0, "pending_review": 0, "pending_approval": 0, "approved": 0, "archived": 0,
    }
    assert body["catalog"]["last_refresh_at"] is None
    assert body["catalog"]["last_snapshot_id"] is None
    assert body["pending"] == {"my_review": 0, "my_approval": 0}
    assert body["users"] is not None
    assert body["users"]["total"] >= 7
    assert body["users"]["active"] >= 7
    assert isinstance(body["recent_operations"], list)


async def test_stats_users_null_for_non_admin(client, headers):
    body = assert_ok(await client.get("/api/stats/overview", headers=headers["engineer01"]), 200)
    assert body.get("users") is None


async def test_stats_after_archive(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]

    body = assert_ok(await client.get("/api/stats/overview", headers=headers["admin"]), 200)
    assert body["files"]["total"] == 1
    assert body["files"]["by_status"]["archived"] == 1
    assert body["catalog"]["last_snapshot_id"] is not None
    assert body["catalog"]["item_count"] == 1
    assert body["catalog"]["last_refresh_at"]
    assert any(item["operation_type"] == "archive" for item in body["recent_operations"])


async def test_stats_pending_counts(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")

    leader_stats = assert_ok(await client.get("/api/stats/overview", headers=headers["leader01"]), 200)
    assert leader_stats["pending"]["my_review"] == 1
    assert leader_stats["pending"]["my_approval"] == 0

    await review(client, headers["leader01"], detail["id"])

    manager_stats = assert_ok(await client.get("/api/stats/overview", headers=headers["manager01"]), 200)
    assert manager_stats["pending"]["my_approval"] == 1

    engineer_stats = assert_ok(await client.get("/api/stats/overview", headers=headers["engineer01"]), 200)
    assert engineer_stats["pending"]["my_review"] == 0
    assert engineer_stats["pending"]["my_approval"] == 0


async def test_stats_counts_are_consistent(client, headers, flow):
    await flow.complete(uploader="engineer01", file_name="统计甲")
    detail = await flow.submit(uploader="engineer02", file_name="统计乙")

    body = assert_ok(await client.get("/api/stats/overview", headers=headers["admin"]), 200)
    by_status = body["files"]["by_status"]
    assert sum(by_status.values()) == body["files"]["total"] == 2
    assert by_status["archived"] == 1
    assert by_status["pending_review"] == 1
