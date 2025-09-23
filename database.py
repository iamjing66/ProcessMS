from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncmy  # 使用 asyncmy 替代 aiomysql 以获得更好的兼容性

from config import settings

# 同步引擎（用于迁移等）
engine = create_engine(
    settings.DATABASE_URL.replace("aiomysql", "pymysql").replace("asyncmy", "pymysql"),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600
)

# 异步引擎（用于应用）- 使用 asyncmy
async_database_url = settings.DATABASE_URL.replace("aiomysql", "asyncmy")
async_engine = create_async_engine(
    async_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600
)

# 会话工厂
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# 数据库初始化函数
async def init_db():
    """初始化数据库表"""
    async with async_engine.begin() as conn:
        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)

async def close_db():
    """关闭数据库连接"""
    await async_engine.dispose()

# 依赖注入
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()