"""FastAPI 应用入口。

启动流程统一在 lifespan 中完成：建目录 -> 建表 -> 幂等种子 -> 可选启动调度器；
import 本模块不会连接数据库、不产生副作用（便于测试与 ASGITransport 使用）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import BASE_DIR, settings
from database import (
    AsyncSessionLocal,
    check_db,
    close_db,
    ensure_database_directory,
    init_db,
)
from init_data import seed_data
from utils.exceptions import AppError

logging.basicConfig(
    level=getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger("processms")


def ensure_directories() -> None:
    """确保上传目录、SQLite 数据目录、日志目录存在。"""
    from utils.file_upload import upload_root

    upload_root()
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期。"""
    if settings.is_default_secret:
        if settings.is_prod:
            raise RuntimeError("生产环境必须通过环境变量设置 SECRET_KEY（至少 32 个字符）")
        logger.warning("当前使用默认开发 SECRET_KEY，请勿用于生产环境")
    if settings.is_prod and settings.ALLOW_REGISTER:
        settings.ALLOW_REGISTER = False
        logger.warning("生产环境强制关闭自助注册（ALLOW_REGISTER=false）")
    ensure_directories()
    ensure_database_directory()
    await init_db()

    async with AsyncSessionLocal() as session:
        try:
            seed_stats = await seed_data(session)
            await session.commit()
            logger.info("种子数据检查完成：%s", seed_stats)
        except Exception:
            await session.rollback()
            logger.exception("种子数据初始化失败")
            raise

    if settings.CATALOG_REFRESH_ON_STARTUP:
        from crud.catalog import refresh_catalog

        async with AsyncSessionLocal() as session:
            try:
                await refresh_catalog(session, refresh_type="auto", operator_id=None)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("启动时刷新文件清单失败")

    from services.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()
        await close_db()
        logger.info("应用已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    description="企业级工艺文件管理平台：上传/版本/审批/签名/归档/清单/检索/审计",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 统一异常处理：{code, message, detail}
# ---------------------------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    detail: dict = {}
    for error in exc.errors():
        location = [
            str(part)
            for part in error.get("loc", [])
            if part not in ("body", "query", "path", "header", "cookie")
        ]
        field = ".".join(location) or "request"
        message = str(error.get("msg", "参数错误"))
        detail.setdefault(field, message)
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "detail": detail,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    mapping = {
        401: ("AUTH_REQUIRED", "请先登录"),
        403: ("FORBIDDEN", "无权执行该操作"),
        404: ("NOT_FOUND", "接口不存在"),
        405: ("METHOD_NOT_ALLOWED", "请求方法不允许"),
    }
    code, default_message = mapping.get(exc.status_code, ("HTTP_ERROR", "请求失败"))
    message = exc.detail if isinstance(exc.detail, str) else default_message
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": message, "detail": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误，请稍后重试",
            "detail": None,
        },
    )


# ---------------------------------------------------------------------------
# 路由注册（统一 /api 前缀）
# ---------------------------------------------------------------------------
from routers.approvals import router as approvals_router  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402
from routers.catalogs import router as catalogs_router  # noqa: E402
from routers.files import router as files_router  # noqa: E402
from routers.logs import router as logs_router  # noqa: E402
from routers.roles import router as roles_router  # noqa: E402
from routers.stats import router as stats_router  # noqa: E402
from routers.users import router as users_router  # noqa: E402

app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
app.include_router(users_router, prefix="/api/users", tags=["用户管理"])
app.include_router(roles_router, prefix="/api", tags=["角色权限"])
app.include_router(files_router, prefix="/api/files", tags=["文件管理"])
app.include_router(approvals_router, prefix="/api/approvals", tags=["审批流程"])
app.include_router(catalogs_router, prefix="/api/catalogs", tags=["文件清单"])
app.include_router(logs_router, prefix="/api/logs", tags=["操作日志"])
app.include_router(stats_router, prefix="/api/stats", tags=["统计"])


@app.get("/", include_in_schema=False)
async def root():
    """根路径重定向到前端管理界面。"""
    return RedirectResponse(url="/ui/", status_code=302)


@app.get("/health", tags=["系统"])
async def health():
    """健康检查：数据库可用返回 200，否则 503。"""
    ok = await check_db()
    payload = {
        "status": "healthy" if ok else "unhealthy",
        "database": "ok" if ok else "error",
        "version": settings.APP_VERSION,
    }
    return JSONResponse(status_code=200 if ok else 503, content=payload)


# 前端静态界面（web/ 由 frontend 提供；不存在时不影响 API）
web_dir = Path(settings.WEB_DIR)
if not web_dir.is_absolute():
    web_dir = BASE_DIR / web_dir
if web_dir.is_dir():

    @app.get("/ui", include_in_schema=False)
    async def ui_redirect():
        return RedirectResponse(url="/ui/", status_code=302)

    app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="ui")
    logger.info("前端静态目录已挂载：%s -> /ui/", web_dir)
