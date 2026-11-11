# -*- coding: utf-8 -*-
"""pytest 全局夹具。

设计目标：
1. 完全基于临时 SQLite 文件库（sqlite+aiosqlite），不依赖真实 MySQL；
2. 不触发应用 lifespan（httpx ASGITransport 不执行 startup），由夹具手动建表 + 种子；
3. 每个用例独立建库、独立数据，可用例顺序无关、可重复执行；
4. 通过 dependency_overrides 注入测试 get_db，保证路由使用测试库；
5. 复用后端 init_data.seed_data 生成角色/权限矩阵与演示账号，保证测试数据与生产种子一致；
   同时额外创建 1 个无角色账号用于 RBAC 用例。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 1) 仓库根目录加入 sys.path，并设置测试环境变量（必须早于导入应用代码）
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="processms_pytest_"))
_TMP_UPLOAD = _TMP_ROOT / "uploads"
_TMP_UPLOAD.mkdir(parents=True, exist_ok=True)

# 测试统一口令（后端 init_data.seed_data 从 settings.SEED_PASSWORD 读取）
TEST_PASSWORD = "Test@12345"

os.environ["ENV"] = "dev"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP_ROOT / 'import_check.db').as_posix()}"
os.environ["SECRET_KEY"] = "pytest-secret-key-0123456789abcdef0123456789abcdef"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"
os.environ["UPLOAD_DIR"] = str(_TMP_UPLOAD)
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["ALLOW_REGISTER"] = "true"
os.environ["SEED_PASSWORD"] = TEST_PASSWORD
# 测试关闭同用户上传冷却，避免用例之间/同一用例多次上传被 429 干扰；
# 专门的限流用例会临时把 settings.UPLOAD_COOLDOWN_SECONDS 改回 2（见 test_upload.py）。
os.environ["UPLOAD_COOLDOWN_SECONDS"] = "0"
# 注意：pydantic-settings 对 List 字段的环境变量会先做 JSON 解析，
# 因此这里用 JSON 数组而不是逗号分隔（.env 的逗号写法会导致 SettingsError）。
os.environ["ALLOWED_ORIGINS"] = '["http://127.0.0.1:8000","http://localhost:3000"]'
os.environ["ALLOWED_EXTENSIONS"] = '[".pdf",".doc",".docx",".xls",".xlsx",".txt"]'

import bcrypt  # noqa: E402
import jwt  # noqa: E402

# 测试加速：把 bcrypt 成本降到最低（4）。后端 utils/security.py 通过 bcrypt 模块调用
# gensalt，因此这里替换模块函数即可同时加速种子哈希与登录校验，不影响算法正确性。
_original_gensalt = bcrypt.gensalt


def _fast_gensalt(rounds: int = 12, prefix: bytes = b"2b"):
    return _original_gensalt(rounds=4, prefix=prefix)


bcrypt.gensalt = _fast_gensalt  # type: ignore[assignment]
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import config as config_module  # noqa: E402
from database import Base, get_db  # noqa: E402



def get_settings():
    """兼容 config.py 暴露 settings 单例或 get_settings() 两种写法。"""
    if hasattr(config_module, "get_settings"):
        return config_module.get_settings()
    return config_module.settings


settings = get_settings()

# ---------------------------------------------------------------------------
# 2) 演示账号与种子数据（与 API.md / PLAN 一致）
# ---------------------------------------------------------------------------
DEMO_PASSWORDS = {
    "admin": TEST_PASSWORD,
    "engineer01": TEST_PASSWORD,
    "engineer02": "Engineer2@123",
    "leader01": TEST_PASSWORD,
    "manager01": TEST_PASSWORD,
    "archivist01": TEST_PASSWORD,
    "norole01": "NoRole@123",
}

# 后端 seed_data 只创建 5 个演示账号；engineer02 / norole01 由夹具补充
EXTRA_USERS = [
    # username, employee_id, real_name, [角色名]
    ("engineer02", "000102", "王工", ["engineer"]),
    ("norole01", "000103", "无角色用户", []),
]

ROLE_DESCRIPTIONS = {
    "admin": "系统管理员",
    "engineer": "工艺员（编制）",
    "leader": "组长（审核）",
    "manager": "主管（批准）",
    "archivist": "资料员（归档/清单）",
}

PERMISSIONS = {
    "upload": ("上传", "新建工艺文件"),
    "update": ("更新", "修改文件/上传新版本"),
    "delete": ("删除", "软删除文件"),
    "review": ("审核", "审核环节通过/驳回"),
    "approve": ("批准", "批准环节通过/驳回"),
    "reject": ("驳回", "驳回动作"),
    "archive": ("归档", "已批准文件归档"),
    "catalog_manage": ("清单管理", "手动刷新文件清单"),
    "user_manage": ("用户管理", "用户/角色管理与全量日志"),
}

ROLE_MATRIX = {
    "admin": list(PERMISSIONS.keys()),
    "engineer": ["upload", "update", "delete"],
    "leader": ["upload", "update", "review", "reject"],
    "manager": ["approve", "reject"],
    "archivist": ["archive", "catalog_manage"],
}


def hash_password(plain: str) -> str:
    """直接使用 bcrypt 生成哈希（与后端 utils/security.py 保持算法一致）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


async def _seed_by_orm(session: AsyncSession):
    """兜底种子（若后端 seed_data 不可用时使用），按 PLAN 创建角色/权限/账号。"""
    from models.user import Permission, Role, RolePermission, User, UserRole

    role_objs = {}
    for name, desc in ROLE_DESCRIPTIONS.items():
        role_obj = Role(name=name, description=desc)
        session.add(role_obj)
        role_objs[name] = role_obj
    await session.flush()

    perm_objs = {}
    for code, (name, desc) in PERMISSIONS.items():
        perm_obj = Permission(code=code, name=name, description=desc)
        session.add(perm_obj)
        perm_objs[code] = perm_obj
    await session.flush()

    for role_name, codes in ROLE_MATRIX.items():
        for code in codes:
            session.add(RolePermission(role_id=role_objs[role_name].id, permission_id=perm_objs[code].id))

    for username in ["admin", "engineer01", "leader01", "manager01", "archivist01"]:
        role_name = {
            "admin": "admin",
            "engineer01": "engineer",
            "leader01": "leader",
            "manager01": "manager",
            "archivist01": "archivist",
        }[username]
        user = User(
            employee_id={"admin": "000001", "engineer01": "000002", "leader01": "000004",
                         "manager01": "000005", "archivist01": "000006"}[username],
            username=username,
            password_hash=hash_password(TEST_PASSWORD),
            real_name={"admin": "系统管理员", "engineer01": "李工", "leader01": "孙组长",
                       "manager01": "赵主管", "archivist01": "周资料员"}[username],
            department="工艺部",
            position="测试岗位",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role_objs[role_name].id))
    await session.flush()


async def seed_database(session: AsyncSession):
    """初始化测试数据：优先后端 seed_data，再补无角色/额外工程师账号；返回 ID 映射。"""
    backend_seed = None
    try:
        from init_data import seed_data as backend_seed  # type: ignore
    except (ImportError, AttributeError):
        backend_seed = None

    if backend_seed is not None:
        await backend_seed(session)
        await session.flush()
    else:
        await _seed_by_orm(session)

    from sqlalchemy import select

    from models.user import Permission, Role, User, UserRole

    # 补齐额外账号
    existing = {
        username for (username,) in (await session.execute(select(User.username))).all()
    }
    for username, employee_id, real_name, role_names in EXTRA_USERS:
        if username in existing:
            continue
        user = User(
            employee_id=employee_id,
            username=username,
            password_hash=hash_password(DEMO_PASSWORDS[username]),
            real_name=real_name,
            department="工艺部",
            position="测试岗位",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        for role_name in role_names:
            role_obj = (
                await session.execute(select(Role).where(Role.name == role_name))
            ).scalar_one()
            session.add(UserRole(user_id=user.id, role_id=role_obj.id))
    await session.flush()

    user_ids = {
        username: uid for username, uid in (await session.execute(select(User.username, User.id))).all()
    }
    role_ids = {name: rid for name, rid in (await session.execute(select(Role.name, Role.id))).all()}
    permission_ids = {
        code: pid for code, pid in (await session.execute(select(Permission.code, Permission.id))).all()
    }
    return {"user_ids": user_ids, "role_ids": role_ids, "permission_ids": permission_ids}


# ---------------------------------------------------------------------------
# 3) 数据库夹具
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def engine(tmp_path):
    """每个用例一个独立的临时 SQLite 文件库。"""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    eng = create_async_engine(url, echo=False, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    """直连测试库的会话，供用例做数据准备/断言。"""
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seed(session_factory):
    """初始化种子数据，返回 ID 映射。"""
    async with session_factory() as session:
        data = await seed_database(session)
        await session.commit()
    return data


# ---------------------------------------------------------------------------
# 4) 上传目录与 HTTP 客户端
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_upload_cooldown():
    """清理 routers.files 的进程内上传冷却状态，避免用例间串扰。"""
    import importlib
    import sys

    module = sys.modules.get("routers.files")
    if module is None:
        try:
            module = importlib.import_module("routers.files")
        except Exception:  # pragma: no cover - 业务代码不可导入时跳过
            module = None
    state = getattr(module, "_upload_last_at", None) if module is not None else None
    if isinstance(state, dict):
        state.clear()
    yield
    if isinstance(state, dict):
        state.clear()

@pytest_asyncio.fixture
async def upload_dir(tmp_path, monkeypatch):
    """把 settings.UPLOAD_DIR 指到临时目录，保证测试不写真实上传目录。"""
    directory = tmp_path / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    current = get_settings()
    monkeypatch.setattr(current, "UPLOAD_DIR", str(directory), raising=False)
    yield directory


@pytest_asyncio.fixture
async def client(seed, session_factory, upload_dir):
    """注入测试库的 ASGI 客户端（等价于真实 HTTP，但不走网络）。"""
    # 延迟导入应用，保证纯函数单元测试在业务代码临时不可导入时也能运行
    from main import app as fastapi_app

    async def override_get_db():
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    # raise_app_exceptions=False：未捕获异常以真实 500 响应返回，便于用例断言与缺陷定位
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    fastapi_app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 5) 令牌夹具：默认用签名正确的 JWT 直构，避免每个用例都跑 bcrypt 登录
# ---------------------------------------------------------------------------
def make_access_token(username: str, uid: int, expires_delta: timedelta | None = None) -> str:
    current = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=120)
    payload = {
        "sub": username,
        "uid": uid,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, current.SECRET_KEY, algorithm=getattr(current, "ALGORITHM", "HS256"))


@pytest.fixture
def auth_headers(seed):
    """auth_headers("engineer01") -> {"Authorization": "Bearer ..."}"""

    def _make(username: str, expires_delta: timedelta | None = None) -> dict:
        uid = seed["user_ids"][username]
        token = make_access_token(username, uid, expires_delta)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def headers(auth_headers):
    """常用账号的认证头集合：headers["admin"]、headers["leader01"] 等。"""
    return {username: auth_headers(username) for username in DEMO_PASSWORDS}


@pytest.fixture
def tokens(headers):
    return headers


@pytest.fixture
def flow(client, headers, seed):
    """审批流便捷封装：默认显式把审核人/批准人指定为 leader01/manager01。"""
    from tests import helpers

    ids = seed["user_ids"]

    class FlowHelper:
        async def upload(self, *, uploader: str = "engineer01", **upload_kwargs):
            return await helpers.upload_file(client, headers[uploader], **upload_kwargs)

        async def submit(self, *, uploader: str = "engineer01", **upload_kwargs):
            return await helpers.upload_and_submit(
                client,
                headers,
                uploader=uploader,
                submit_payload={"reviewer_id": ids["leader01"], "approver_id": ids["manager01"]},
                **upload_kwargs,
            )

        async def complete(self, **kwargs):
            kwargs.setdefault("reviewer_id", ids["leader01"])
            kwargs.setdefault("approver_id", ids["manager01"])
            return await helpers.complete_flow(client, headers, **kwargs)
    return FlowHelper()