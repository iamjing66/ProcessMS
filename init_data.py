"""初始化数据：5 角色、9 权限、角色权限矩阵、演示账号（异步幂等）。

- 角色/权限/矩阵：每次启动都会校正（幂等），任何环境均执行；
- 演示账号：仅 ENV=dev 或显式 SEED_DEMO_USERS=true 时创建；
  必须提供 SEED_PASSWORD（否则跳过并告警），密码只来自环境变量，
  默认演示密码仅出现在 .env.example 与 README 的开发说明中。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import Permission, Role, RolePermission, User, UserRole
from utils.security import hash_password
from utils.time import utcnow

logger = logging.getLogger("processms.seed")

# (权限码, 名称, 描述) —— 顺序与 API 契约 §2.8 一致
PERMISSION_SEEDS = [
    ("upload", "上传", "新建工艺文件"),
    ("update", "更新", "修改文件/上传新版本"),
    ("delete", "删除", "软删除文件"),
    ("review", "审核", "审核环节通过/驳回"),
    ("approve", "批准", "批准环节通过/驳回"),
    ("reject", "驳回", "驳回动作"),
    ("archive", "归档", "已批准文件归档"),
    ("catalog_manage", "清单管理", "手动刷新文件清单"),
    ("user_manage", "用户管理", "用户/角色管理与全量日志"),
]

# 角色-权限矩阵（PLAN §7.2）
ROLE_SEEDS = [
    {
        "name": "admin",
        "description": "系统管理员",
        "permissions": [code for code, _, _ in PERMISSION_SEEDS],
    },
    {
        "name": "engineer",
        "description": "工艺员（编制）",
        "permissions": ["upload", "update", "delete"],
    },
    {
        "name": "leader",
        "description": "组长（审核）",
        "permissions": ["upload", "update", "review", "reject"],
    },
    {
        "name": "manager",
        "description": "主管（批准）",
        "permissions": ["approve", "reject"],
    },
    {
        "name": "archivist",
        "description": "资料员（归档/清单）",
        "permissions": ["archive", "catalog_manage"],
    },
]

# 演示账号（仅开发/显式开启时创建）
DEMO_USERS = [
    {
        "employee_id": "000001",
        "username": "admin",
        "real_name": "系统管理员",
        "department": "信息部",
        "position": "系统管理员",
        "role": "admin",
    },
    {
        "employee_id": "000002",
        "username": "engineer01",
        "real_name": "李工",
        "department": "工艺部",
        "position": "工艺员",
        "role": "engineer",
    },
    {
        "employee_id": "000003",
        "username": "leader01",
        "real_name": "孙组长",
        "department": "工艺部",
        "position": "组长",
        "role": "leader",
    },
    {
        "employee_id": "000004",
        "username": "manager01",
        "real_name": "赵主管",
        "department": "工艺部",
        "position": "主管",
        "role": "manager",
    },
    {
        "employee_id": "000005",
        "username": "archivist01",
        "real_name": "周资料员",
        "department": "资料室",
        "position": "资料员",
        "role": "archivist",
    },
]


async def _seed_permissions(session: AsyncSession) -> Dict[str, Permission]:
    result = await session.execute(select(Permission))
    existing = {item.code: item for item in result.scalars().all()}
    for code, name, description in PERMISSION_SEEDS:
        permission = existing.get(code)
        if permission is None:
            permission = Permission(code=code, name=name, description=description)
            session.add(permission)
            existing[code] = permission
        else:
            permission.name = name
            permission.description = description
    await session.flush()
    return existing


async def _seed_roles(
    session: AsyncSession, permissions: Dict[str, Permission]
) -> Dict[str, Role]:
    result = await session.execute(select(Role))
    existing = {item.name: item for item in result.scalars().all()}
    for spec in ROLE_SEEDS:
        role = existing.get(spec["name"])
        if role is None:
            role = Role(name=spec["name"], description=spec["description"], created_at=utcnow())
            session.add(role)
            existing[spec["name"]] = role
        else:
            role.description = spec["description"]
    await session.flush()

    # 校正角色-权限矩阵（删除多余关联、补齐缺失关联）
    for spec in ROLE_SEEDS:
        role = existing[spec["name"]]
        desired_codes = set(spec["permissions"])
        desired_ids = {permissions[code].id for code in desired_codes}
        result = await session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        current = list(result.scalars().all())
        current_ids = {item.permission_id for item in current}
        for item in current:
            if item.permission_id not in desired_ids:
                await session.delete(item)
        for permission_id in desired_ids - current_ids:
            session.add(RolePermission(role_id=role.id, permission_id=permission_id))
    await session.flush()
    return existing


async def _seed_demo_users(
    session: AsyncSession, roles: Dict[str, Role]
) -> int:
    demo_enabled = bool(settings.SEED_DEMO_USERS) or settings.ENV.lower() == "dev"
    if not demo_enabled:
        logger.info("未启用演示账号（SEED_DEMO_USERS=false 且 ENV!=dev）")
        return 0
    if not settings.SEED_PASSWORD:
        logger.warning(
            "未设置 SEED_PASSWORD，已跳过演示账号创建。"
            "请参考 .env.example 在 .env 中设置 SEED_PASSWORD（仅开发/演示环境使用）。"
        )
        return 0

    created = 0
    for spec in DEMO_USERS:
        result = await session.execute(
            select(User).where(User.username == spec["username"])
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                employee_id=spec["employee_id"],
                username=spec["username"],
                password_hash=hash_password(settings.SEED_PASSWORD),
                real_name=spec["real_name"],
                department=spec["department"],
                position=spec["position"],
                is_active=True,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(user)
            await session.flush()
            created += 1
        role = roles.get(spec["role"])
        if role is None:
            continue
        result = await session.execute(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()
    return created


async def seed_data(session: AsyncSession) -> dict:
    """幂等种子入口（只 flush，由调用方 commit），供启动流程与测试复用。"""
    permissions = await _seed_permissions(session)
    roles = await _seed_roles(session, permissions)
    created_users = await _seed_demo_users(session, roles)
    await session.flush()
    return {
        "permissions": len(permissions),
        "roles": len(roles),
        "demo_users_created": created_users,
        "demo_enabled": bool(settings.SEED_DEMO_USERS) or settings.ENV.lower() == "dev",
    }


# 兼容测试/脚本命名
seed_all = seed_data


async def _main() -> None:
    from database import AsyncSessionLocal, close_db, ensure_database_directory, init_db

    await init_db()
    ensure_database_directory()
    async with AsyncSessionLocal() as session:
        result = await seed_data(session)
        await session.commit()
    await close_db()
    print(f"初始化完成：{result}")
    if settings.SEED_PASSWORD:
        print("演示账号：admin/engineer01/leader01/manager01/archivist01（密码取自 SEED_PASSWORD）")


if __name__ == "__main__":
    asyncio.run(_main())
