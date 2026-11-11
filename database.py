"""数据库连接模块。

统一使用 SQLAlchemy 2.0 异步 API，同时支持：
- MySQL：mysql+aiomysql://user:password@host:3306/db?charset=utf8mb4
- SQLite：sqlite+aiosqlite:///./dev.db（开发/测试）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import unquote

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def normalize_database_url(url: str) -> str:
    """规范化数据库连接串，自动补全异步驱动。"""
    url = (url or "").strip()
    if url.startswith("mysql://"):
        url = "mysql+aiomysql://" + url[len("mysql://"):]
    elif url.startswith("sqlite:///") and "aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


DATABASE_URL = normalize_database_url(settings.DATABASE_URL)
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def _build_engine_kwargs() -> dict:
    """按数据库类型生成引擎参数。"""
    kwargs: dict = {"echo": settings.DATABASE_ECHO, "future": True}
    if IS_SQLITE:
        # SQLite 不支持连接池参数，仅需允许跨线程使用
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            pool_pre_ping=True,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
        )
    return kwargs


async_engine = create_async_engine(DATABASE_URL, **_build_engine_kwargs())

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# 便于测试/脚本引用的别名
async_session_maker = AsyncSessionLocal


if IS_SQLITE:

    @event.listens_for(async_engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # pragma: no cover
        """SQLite 默认不启用外键，这里显式开启。"""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供异步数据库会话，异常时自动回滚。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def sqlite_file_path(url: str = DATABASE_URL) -> Optional[Path]:
    """从 SQLite 连接串中解析数据库文件绝对路径（用于自动建目录）。"""
    if not url.startswith("sqlite"):
        return None
    if ":///" not in url:
        return None
    raw = url.split(":///", 1)[1].split("?", 1)[0]
    raw = unquote(raw)
    if not raw or raw == ":memory:":
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def ensure_database_directory() -> None:
    """SQLite 模式下确保数据库文件所在目录存在。"""
    path = sqlite_file_path()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    """创建所有数据库表（若不存在）。"""
    # 确保所有模型模块被导入，元数据完整
    import models  # noqa: F401

    ensure_database_directory()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表初始化完成：%s", DATABASE_URL)


async def close_db() -> None:
    """释放数据库连接池。"""
    await async_engine.dispose()
    logger.info("数据库连接已关闭")


async def check_db() -> bool:
    """探测数据库连通性，供健康检查使用。"""
    from sqlalchemy import text

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - 依赖真实数据库
        logger.warning("数据库连接检测失败：%s", exc)
        return False
