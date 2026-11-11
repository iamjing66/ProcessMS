# -*- coding: utf-8 -*-
"""RBAC 用例：角色权限矩阵与资源级越权。"""
from __future__ import annotations

from tests.conftest import make_access_token
from tests.helpers import assert_error, assert_ok, get_file, upload_file, upload_and_submit


async def _create_user(client, headers, seed, username: str, role_names: list[str], employee_id: str) -> dict:
    resp = await client.post(
        "/api/users",
        headers=headers["admin"],
        json={
            "employee_id": employee_id,
            "username": username,
            "password": "Passw0rd",
            "real_name": f"{username}姓名",
            "role_ids": [seed["role_ids"][name] for name in role_names],
            "is_active": True,
        },
    )
    return assert_ok(resp, 201)


async def test_engineer_cannot_manage_users_or_read_logs(client, headers, seed):
    """engineer 无 user_manage：用户/角色/权限/全量日志均 403。"""
    cases = [
        ("get", "/api/users", None),
        ("post", "/api/users", {
            "employee_id": "000900", "username": "x1", "password": "Passw0rd", "real_name": "X"
        }),
        ("get", "/api/roles", None),
        ("get", "/api/permissions", None),
        ("get", "/api/logs", None),
        ("put", f"/api/users/{seed['user_ids']['engineer02']}", {"is_active": False}),
        ("delete", f"/api/users/{seed['user_ids']['engineer02']}", None),
    ]
    for method, path, payload in cases:
        resp = await client.request(method, path, headers=headers["engineer01"], json=payload)
        assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_engineer_cannot_review_approve_archive_or_refresh_catalog(client, headers):
    detail = await upload_and_submit(client, headers, uploader="engineer01")
    file_id = detail["id"]

    for path, payload in [
        (f"/api/files/{file_id}/review", {"result": "pass", "comment": "越权审核"}),
        (f"/api/files/{file_id}/approve", {"result": "pass", "comment": "越权批准"}),
        (f"/api/files/{file_id}/archive", {"comment": "越权归档"}),
    ]:
        resp = await client.post(path, headers=headers["engineer01"], json=payload)
        assert_error(resp, 403, "FORBIDDEN_PERMISSION")

    resp = await client.post("/api/catalogs/refresh", headers=headers["engineer01"], json={})
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_manager_cannot_upload_or_review(client, headers):
    resp = await client.post(
        "/api/files/upload",
        headers=headers["manager01"],
        data={"file_name": "主管上传", "process_step": "车削"},
        files={"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")

    detail = await upload_and_submit(client, headers, uploader="engineer01")
    resp = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["manager01"],
        json={"result": "pass", "comment": "越权审核"},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_leader_can_upload_and_review_but_not_approve(client, headers, flow):
    """leader 有 upload/review/reject，无 approve/archive/catalog_manage。"""
    detail = await flow.submit(uploader="leader01")
    file_id = detail["id"]
    reviewed = await client.post(
        f"/api/files/{file_id}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "审核通过"},
    )
    assert_ok(reviewed, 200)

    resp = await client.post(
        f"/api/files/{file_id}/approve",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "越权批准"},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")

    resp = await client.post(f"/api/files/{file_id}/archive", headers=headers["leader01"], json={})
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_archivist_can_archive_and_refresh_but_not_upload(client, headers, flow):
    import asyncio
    resp = await client.post(
        "/api/files/upload",
        headers=headers["archivist01"],
        data={"file_name": "资料员上传", "process_step": "车削"},
        files={"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")

    result = await flow.complete(uploader="engineer01")
    assert result["file"]["file_status"] == 5

    await asyncio.sleep(1.05)  # 跨秒，避免复用归档触发同秒 auto 快照
    resp = await client.post("/api/catalogs/refresh", headers=headers["archivist01"], json={})
    body = assert_ok(resp, 200)
    assert body["snapshot"]["refresh_type"] == "manual"


async def test_admin_has_all_permissions(client, headers):
    for path in ["/api/users", "/api/roles", "/api/permissions", "/api/logs"]:
        resp = await client.get(path, headers=headers["admin"])
        assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:300]}"

    roles = (await client.get("/api/roles", headers=headers["admin"])).json()
    assert isinstance(roles, list) and len(roles) == 5
    perms = (await client.get("/api/permissions", headers=headers["admin"])).json()
    assert isinstance(perms, list) and len(perms) == 9

    resp = await client.post("/api/catalogs/refresh", headers=headers["admin"], json={})
    assert_ok(resp, 200)


async def test_no_role_user_has_no_business_permissions(client, headers):
    resp = await client.get("/api/auth/me", headers=headers["norole01"])
    body = assert_ok(resp, 200)
    assert body["permissions"] == []
    assert body["roles"] == []

    resp = await client.get("/api/files", headers=headers["norole01"])
    assert_ok(resp, 200)  # 登录用户可看「可见集合」

    resp = await client.post(
        "/api/files/upload",
        headers=headers["norole01"],
        data={"file_name": "无角色上传", "process_step": "车削"},
        files={"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_engineer_cannot_update_or_delete_others_draft(client, headers, seed):
    detail = await upload_file(client, headers["engineer01"], file_name="engineer01 草稿")
    file_id = detail["id"]

    # 草稿对非本人不可见 → 统一 404（API.md §0.7，避免探测存在性）
    resp = await client.put(
        f"/api/files/{file_id}",
        headers=headers["engineer02"],
        data={"file_name": "被别人改名"},
    )
    assert_error(resp, 404, "FILE_NOT_FOUND")

    resp = await client.delete(f"/api/files/{file_id}", headers=headers["engineer02"])
    assert_error(resp, 404, "FILE_NOT_FOUND")


async def test_not_current_approver_forbidden(client, headers, seed, flow):
    """再建一个 leader，非当前步骤审批人不能审核。"""
    created = await _create_user(client, headers, seed, "leader02", ["leader"], "000202")
    leader02_headers = {"Authorization": f"Bearer {make_access_token('leader02', created['id'])}"}

    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]

    resp = await client.post(
        f"/api/files/{file_id}/review",
        headers=leader02_headers,
        json={"result": "pass", "comment": "不是我的待办"},
    )
    assert_error(resp, 403, "NOT_CURRENT_APPROVER")


async def test_assign_reviewer_without_permission_rejected(client, headers, seed):
    """提交时指定的审核人必须拥有 review 权限。"""
    detail = await upload_file(client, headers["engineer01"])
    resp = await client.post(
        f"/api/files/{detail['id']}/submit-review",
        headers=headers["engineer01"],
        json={"reviewer_id": seed["user_ids"]["engineer02"]},
    )
    assert resp.status_code in (400, 403, 404, 422), f"期望拒绝，实际 {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body["code"] in {"VALIDATION_ERROR", "FORBIDDEN", "FORBIDDEN_PERMISSION", "USER_NOT_FOUND"}


async def test_file_visibility_of_draft(client, headers):
    """草稿仅 owner/审批人/admin 可见，其他工程师详情 404。"""
    detail = await upload_file(client, headers["engineer01"], file_name="草稿可见性")
    file_id = detail["id"]

    assert_ok(await client.get(f"/api/files/{file_id}", headers=headers["engineer01"]), 200)
    assert_ok(await client.get(f"/api/files/{file_id}", headers=headers["admin"]), 200)
    assert_error(await client.get(f"/api/files/{file_id}", headers=headers["engineer02"]), 404, "FILE_NOT_FOUND")

async def test_reject_requires_reject_permission(client, headers, seed, db_session, flow):
    """只有 review 权限、没有 reject 权限的用户：可审核通过，但不能驳回。"""
    from sqlalchemy import delete, select

    from models.user import Permission, Role, RolePermission

    leader_role = (await db_session.execute(select(Role).where(Role.name == "leader"))).scalar_one()
    reject_perm = (
        await db_session.execute(select(Permission).where(Permission.code == "reject"))
    ).scalar_one()
    await db_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == leader_role.id,
            RolePermission.permission_id == reject_perm.id,
        )
    )
    await db_session.commit()

    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]

    resp = await client.post(
        f"/api/files/{file_id}/review",
        headers=headers["leader01"],
        json={"result": "reject", "comment": "无驳回权限"},
    )
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")

    # 文件仍停在待审核，review 通过应成功
    assert (await get_file(client, headers["engineer01"], file_id))["file_status"] == 2
    passed = await client.post(
        f"/api/files/{file_id}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "通过"},
    )
    assert_ok(passed, 200)
