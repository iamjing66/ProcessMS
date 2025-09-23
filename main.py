from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

from config import settings
from database import init_db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 确保必要的目录存在
def ensure_directories():
    """确保必要的目录存在"""
    directories = [settings.UPLOAD_DIR, "logs"]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"创建目录: {directory}")

# 在应用启动前创建目录
ensure_directories()

# 初始化数据库
init_db()
logger.info("数据库初始化完成")

# 创建FastAPI应用
app = FastAPI(
    title="工艺文件管理系统",
    description="企业级工艺文件管理平台",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 导入并包含路由
try:
    from routers.auth import router as auth_router
    from routers.users import router as users_router
    from routers.files import router as files_router
    
    app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
    app.include_router(users_router, prefix="/api/users", tags=["用户管理"])
    app.include_router(files_router, prefix="/api/files", tags=["文件管理"])
    
    logger.info("路由加载成功")
except ImportError as e:
    logger.error(f"路由加载失败: {e}")

@app.get("/")
async def root():
    return {"message": "工艺文件管理系统 API", "version": "2.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)