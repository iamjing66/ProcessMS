# -*- coding: utf-8 -*-
"""认证用例：登录、令牌、me、改密、注册。"""
from __future__ import annotations

from datetime import timedelta

from tests.conftest import DEMO_PASSWORDS, make_access_token
from tests.helpers import assert_error, assert_ok, login


async def test_login_success(client):
    resp = await login(client, "admin", DEMO_PASSWORDS["admin"])
    body = assert_ok(resp, 200)
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert isinstance(body["expires_in"], int) and body["expires_in"] > 0
    user = body["user"]
    assert user["username"] == "admin"
    assert user["is_active"] is True
    role_names = {role["name"] for role in user["roles"]}
    assert "admin" in role_names


async def test_login_wrong_password(client):
    resp = await login(client, "admin", "wrong-password")
    assert_error(resp, 401, "AUTH_INVALID_CREDENTIALS")


async def test_login_unknown_user(client):
    resp = await login(client, "not-exists-user", "whatever")
    assert_error(resp, 401, "AUTH_INVALID_CREDENTIALS")


async def test_login_missing_field_validation(client):
    resp = await client.post("/api/auth/login", json={"username": "admin"})
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_login_disabled_user(client, db_session, seed):
    """禁用用户（密码正确）不能登录。"""
    from sqlalchemy import update

    from models.user import User

    await db_session.execute(update(User).where(User.username == "engineer02").values(is_active=False))
    await db_session.commit()

    resp = await login(client, "engineer02", DEMO_PASSWORDS["engineer02"])
    assert_error(resp, 403, "AUTH_USER_DISABLED")


async def test_me_returns_profile_and_permissions(client, headers):
    resp = await client.get("/api/auth/me", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["username"] == "admin"
    assert set(body["permissions"]) == {
        "upload", "update", "delete", "review", "approve", "reject", "archive", "catalog_manage", "user_manage",
    }
    assert [role["name"] for role in body["roles"]] == ["admin"]


async def test_me_engineer_permissions(client, headers):
    resp = await client.get("/api/auth/me", headers=headers["engineer01"])
    body = assert_ok(resp, 200)
    assert set(body["permissions"]) == {"upload", "update", "delete"}


async def test_me_requires_token(client):
    resp = await client.get("/api/auth/me")
    assert_error(resp, 401, "AUTH_REQUIRED")


async def test_me_invalid_token(client):
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert_error(resp, 401, "AUTH_TOKEN_INVALID")


async def test_me_expired_token(client, auth_headers):
    expired = auth_headers("engineer01", expires_delta=timedelta(minutes=-5))
    resp = await client.get("/api/auth/me", headers=expired)
    assert_error(resp, 401, "AUTH_TOKEN_EXPIRED")


async def test_me_disabled_user_old_token(client, auth_headers, db_session):
    """用户被禁用后，已签发 token 立即失效。"""
    from sqlalchemy import update

    from models.user import User

    resp = await client.get("/api/auth/me", headers=auth_headers("engineer02"))
    assert resp.status_code == 200

    await db_session.execute(update(User).where(User.username == "engineer02").values(is_active=False))
    await db_session.commit()

    resp = await client.get("/api/auth/me", headers=auth_headers("engineer02"))
    assert_error(resp, 403, "AUTH_USER_DISABLED")


async def test_change_password_success_and_relogin(client, headers):
    resp = await client.post(
        "/api/auth/change-password",
        headers=headers["engineer01"],
        json={"old_password": DEMO_PASSWORDS["engineer01"], "new_password": "NewPass@123"},
    )
    assert_ok(resp, 200)

    old_login = await login(client, "engineer01", DEMO_PASSWORDS["engineer01"])
    assert_error(old_login, 401, "AUTH_INVALID_CREDENTIALS")

    new_login = await login(client, "engineer01", "NewPass@123")
    assert_ok(new_login, 200)


async def test_change_password_wrong_old(client, headers):
    resp = await client.post(
        "/api/auth/change-password",
        headers=headers["engineer01"],
        json={"old_password": "bad-old-password", "new_password": "NewPass@123"},
    )
    assert_error(resp, 400, "INVALID_OLD_PASSWORD")


async def test_change_password_same(client, headers):
    resp = await client.post(
        "/api/auth/change-password",
        headers=headers["engineer01"],
        json={"old_password": DEMO_PASSWORDS["engineer01"], "new_password": DEMO_PASSWORDS["engineer01"]},
    )
    assert_error(resp, 400, "SAME_PASSWORD")


async def test_change_password_too_short(client, headers):
    resp = await client.post(
        "/api/auth/change-password",
        headers=headers["engineer01"],
        json={"old_password": DEMO_PASSWORDS["engineer01"], "new_password": "123"},
    )
    assert_error(resp, 400, "PASSWORD_INVALID")


async def test_register_success(client):
    payload = {
        "employee_id": "000101",
        "username": "zhangsan",
        "password": "Passw0rd",
        "real_name": "张三",
        "department": "工艺部",
        "position": "工艺员",
    }
    resp = await client.post("/api/auth/register", json=payload)
    body = assert_ok(resp, 201)
    assert body["username"] == "zhangsan"
    assert body["employee_id"] == "000101"
    assert body["is_active"] is True
    assert [role["name"] for role in body["roles"]] == ["engineer"]

    login_resp = await login(client, "zhangsan", "Passw0rd")
    assert_ok(login_resp, 200)


async def test_register_duplicate_username(client):
    payload = {
        "employee_id": "000102",
        "username": "admin",
        "password": "Passw0rd",
        "real_name": "重复用户",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert_error(resp, 409, "DUPLICATE_USERNAME")


async def test_register_duplicate_employee_id(client):
    payload = {
        "employee_id": "000001",
        "username": "newuser01",
        "password": "Passw0rd",
        "real_name": "重复工号",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert_error(resp, 409, "DUPLICATE_EMPLOYEE_ID")


async def test_register_disabled_by_config(client, monkeypatch):
    from tests.conftest import get_settings

    monkeypatch.setattr(get_settings(), "ALLOW_REGISTER", False, raising=False)
    payload = {
        "employee_id": "000103",
        "username": "newuser02",
        "password": "Passw0rd",
        "real_name": "未开放注册",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert_error(resp, 403, "REGISTER_DISABLED")


async def test_register_password_too_short(client):
    payload = {
        "employee_id": "000104",
        "username": "newuser03",
        "password": "123",
        "real_name": "短密码",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert_error(resp, 400, "PASSWORD_INVALID")


async def test_register_validation_missing_fields(client):
    resp = await client.post("/api/auth/register", json={"username": "onlyname"})
    assert_error(resp, 422, "VALIDATION_ERROR")
