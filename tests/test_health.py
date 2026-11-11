# -*- coding: utf-8 -*-
"""系统类接口：健康检查、根路径重定向。"""
from __future__ import annotations

from tests.helpers import assert_error


async def test_health_ok(client):
    """健康检查应返回 200，且声明数据库可用。"""
    resp = await client.get("/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


async def test_root_redirects_to_ui(client):
    """根路径 302 到管理界面入口。"""
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 302, resp.text
    assert resp.headers.get("location", "").startswith("/ui")


async def test_unknown_route_404(client):
    resp = await client.get("/api/not-exists")
    assert resp.status_code == 404, resp.text
