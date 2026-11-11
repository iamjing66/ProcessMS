# -*- coding: utf-8 -*-
"""用户与角色管理用例（admin）。"""
from __future__ import annotations

from tests.conftest import DEMO_PASSWORDS, TEST_PASSWORD
from tests.helpers import assert_error, assert_ok, login


async def _user_payload(seed, *, username="newbie01", employee_id="000301", role_names=("engineer",), password="Passw0rd") -> dict:
    return {
        "employee_id": employee_id,
        "username": username,
        "password": password,
        "real_name": "新同事",
        "department": "工艺部",
        "position": "工艺员",
        "role_ids": [seed["role_ids"][name] for name in role_names],
        "is_active": True,
    }


async def test_admin_list_users_paged(client, headers):
    resp = await client.get("/api/users?page=1&size=3", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["page"] == 1 and body["size"] == 3
    assert isinstance(body["items"], list) and len(body["items"]) <= 3
    assert body["total"] >= 6
    assert body["pages"] == (body["total"] + 2) // 3
    item = body["items"][0]
    for field in ["id", "employee_id", "username", "real_name", "is_active", "roles"]:
        assert field in item


async def test_admin_create_user(client, headers, seed):
    resp = await client.post("/api/users", headers=headers["admin"], json=await _user_payload(seed))
    body = assert_ok(resp, 201)
    assert body["username"] == "newbie01"
    assert [role["name"] for role in body["roles"]] == ["engineer"]

    created_id = body["id"]
    detail = await client.get(f"/api/users/{created_id}", headers=headers["admin"])
    assert_ok(detail, 200)


async def test_admin_create_user_duplicate_username(client, headers, seed):
    payload = await _user_payload(seed, username="admin", employee_id="000302")
    resp = await client.post("/api/users", headers=headers["admin"], json=payload)
    assert_error(resp, 409, "DUPLICATE_USERNAME")


async def test_admin_create_user_duplicate_employee_id(client, headers, seed):
    payload = await _user_payload(seed, username="newbie02", employee_id="000001")
    resp = await client.post("/api/users", headers=headers["admin"], json=payload)
    assert_error(resp, 409, "DUPLICATE_EMPLOYEE_ID")


async def test_admin_create_user_invalid_role(client, headers, seed):
    payload = await _user_payload(seed, username="newbie03", employee_id="000303")
    payload["role_ids"] = [99999]
    resp = await client.post("/api/users", headers=headers["admin"], json=payload)
    assert_error(resp, 404, "ROLE_NOT_FOUND")


async def test_user_can_read_self_but_not_others(client, headers, seed):
    own_id = seed["user_ids"]["engineer01"]
    resp = await client.get(f"/api/users/{own_id}", headers=headers["engineer01"])
    assert_ok(resp, 200)

    other_id = seed["user_ids"]["engineer02"]
    resp = await client.get(f"/api/users/{other_id}", headers=headers["engineer01"])
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_admin_update_user(client, headers, seed):
    target = seed["user_ids"]["norole01"]
    resp = await client.put(
        f"/api/users/{target}",
        headers=headers["admin"],
        json={"real_name": "改名之后", "department": "技术部", "is_active": True},
    )
    body = assert_ok(resp, 200)
    assert body["real_name"] == "改名之后"
    assert body["department"] == "技术部"


async def test_admin_replace_user_roles(client, headers, seed):
    target = seed["user_ids"]["norole01"]
    resp = await client.put(
        f"/api/users/{target}/roles",
        headers=headers["admin"],
        json={"role_ids": [seed["role_ids"]["leader"], seed["role_ids"]["archivist"]]},
    )
    body = assert_ok(resp, 200)
    assert {role["name"] for role in body["roles"]} == {"leader", "archivist"}


async def test_admin_disable_user_blocks_login(client, headers, seed):
    target = seed["user_ids"]["engineer02"]
    resp = await client.delete(f"/api/users/{target}", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["id"] == target

    login_resp = await login(client, "engineer02", DEMO_PASSWORDS["engineer02"])
    assert_error(login_resp, 403, "AUTH_USER_DISABLED")


async def test_admin_cannot_disable_self(client, headers, seed):
    admin_id = seed["user_ids"]["admin"]
    resp = await client.delete(f"/api/users/{admin_id}", headers=headers["admin"])
    assert_error(resp, 409, "CANNOT_DISABLE_SELF")


async def test_admin_cannot_remove_last_admin_role(client, headers, seed):
    admin_id = seed["user_ids"]["admin"]
    resp = await client.put(
        f"/api/users/{admin_id}/roles",
        headers=headers["admin"],
        json={"role_ids": [seed["role_ids"]["engineer"]]},
    )
    assert_error(resp, 409, "LAST_ADMIN_PROTECTED")


async def test_admin_user_keyword_filter(client, headers):
    resp = await client.get("/api/users?keyword=leader&page=1&size=10", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["total"] >= 1
    assert all("leader" in (item["username"] + item["real_name"] + item["employee_id"]) for item in body["items"])


async def test_admin_user_not_found(client, headers):
    resp = await client.get("/api/users/999999", headers=headers["admin"])
    assert_error(resp, 404, "USER_NOT_FOUND")


async def test_roles_and_permissions_contract(client, headers):
    roles = assert_ok(await client.get("/api/roles", headers=headers["admin"]), 200)
    assert {role["name"] for role in roles} == {"admin", "engineer", "leader", "manager", "archivist"}
    for role in roles:
        assert {"id", "name", "description"} <= set(role.keys())

    perms = assert_ok(await client.get("/api/permissions", headers=headers["admin"]), 200)
    assert {perm["code"] for perm in perms} == {
        "upload", "update", "delete", "review", "approve", "reject", "archive", "catalog_manage", "user_manage",
    }
