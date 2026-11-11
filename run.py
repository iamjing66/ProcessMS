#!/usr/bin/env python3
"""本地启动脚本：python run.py（默认读取 .env 配置）。"""
from __future__ import annotations

import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=int(settings.PORT),
        reload=bool(settings.RELOAD),
        log_level=str(settings.LOG_LEVEL).lower(),
        workers=None if settings.RELOAD else 1,
    )
