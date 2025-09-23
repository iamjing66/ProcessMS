import os
from typing import List, Optional
try:
    # 尝试从 pydantic-settings 导入（新版本）
    from pydantic_settings import BaseSettings
except ImportError:
    # 回退到 pydantic 的 BaseSettings（旧版本）
    from pydantic import BaseSettings

class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost/process_file_system"
    
    # JWT配置
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 文件上传配置
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"]
    
    # CORS配置
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # 系统配置
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()