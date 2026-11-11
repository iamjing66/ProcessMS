"""全局配置模块（pydantic-settings v2）。

所有配置项均可通过环境变量或项目根目录下的 .env 文件覆盖。
生产环境务必设置 SECRET_KEY 与 DATABASE_URL；开发环境可使用 SQLite。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# NoDecode：禁止 pydantic-settings 对复杂字段做 JSON 预解析，
# 允许 .env 中使用逗号分隔写法（如 ALLOWED_ORIGINS=http://a,http://b）
ListStr = Annotated[List[str], NoDecode]

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SECRET_KEY = "dev-secret-key-please-change-me-in-production"


def _as_str_list(value: Any) -> List[str]:
    """把环境变量中的列表（JSON 数组或逗号分隔）解析为字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return [str(item) for item in json.loads(text)]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


class Settings(BaseSettings):
    """系统配置，字段名即环境变量名（区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- 应用基础 ----------
    ENV: str = "dev"  # dev / prod
    APP_NAME: str = "工艺文件管理系统"
    APP_VERSION: str = "2.0.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False

    # ---------- 数据库 ----------
    # 开发默认 SQLite（零配置可跑）；生产通过 .env 配置 MySQL，例如：
    # DATABASE_URL=mysql+aiomysql://user:password@127.0.0.1:3306/process_file_system?charset=utf8mb4
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/processms.db"
    DATABASE_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600

    # ---------- 安全 / JWT ----------
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    ALLOW_REGISTER: bool = False  # 生产默认关闭；开发环境在 .env 中设为 true

    # ---------- 文件上传 ----------
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: ListStr = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"]
    UPLOAD_CHUNK_SIZE: int = 1024 * 1024
    UPLOAD_COOLDOWN_SECONDS: int = 2

    # ---------- 文件编号 ----------
    # 编号格式：工序代码-YYYYMM-4位流水号，例如 CN-202611-0001
    FILE_NUMBER_SEQ_LENGTH: int = 4
    DEFAULT_PROCESS_CODE: str = "GEN"
    # ---------- 文件清单 ----------
    ENABLE_SCHEDULER: bool = True
    CATALOG_TZ: str = "Asia/Shanghai"
    CATALOG_REFRESH_HOUR: int = 0  # 每天 0 点自动刷新
    CATALOG_REFRESH_ON_STARTUP: bool = False

    # ---------- CORS / 前端静态目录 ----------
    ALLOWED_ORIGINS: ListStr = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    WEB_DIR: str = "web"

    # ---------- 种子数据 ----------
    SEED_DEMO_USERS: bool = False  # ENV=dev 时默认启用；生产显式开启时必须提供 SEED_PASSWORD
    SEED_PASSWORD: str = ""

    # ---------- 校验器 ----------
    @field_validator("ALLOWED_ORIGINS", "ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def _parse_list_fields(cls, value: Any) -> List[str]:
        return _as_str_list(value)

    @field_validator("ALLOWED_EXTENSIONS")
    @classmethod
    def _normalize_extensions(cls, value: List[str]) -> List[str]:
        normalized: List[str] = []
        for ext in value:
            ext = ext.strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = "." + ext
            normalized.append(ext)
        return normalized

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() in ("prod", "production")

    @property
    def is_default_secret(self) -> bool:
        """是否仍在使用默认开发密钥（生产环境应拒绝启动）。"""
        return self.SECRET_KEY == DEFAULT_SECRET_KEY


settings = Settings()