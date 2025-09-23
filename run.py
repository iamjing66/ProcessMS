#!/usr/bin/env python3
"""
工艺文件管理系统启动脚本
可以直接运行: python run.py
"""

import uvicorn
from main import app

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )