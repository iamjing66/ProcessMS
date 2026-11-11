# -*- coding: utf-8 -*-
"""进程级冒烟 pytest 包装。

默认跳过（避免单测阶段反复起服务）；显式运行：
    $env:RUN_SMOKE="1"; python -m pytest tests/smoke -q
或直接执行脚本：
    python tests/smoke/run_smoke.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
@pytest.mark.skipif(os.environ.get("RUN_SMOKE") != "1", reason="设置 RUN_SMOKE=1 后运行进程级冒烟")
def test_process_level_smoke():
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "smoke" / "run_smoke.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"冒烟失败：\nstdout:\n{result.stdout[-6000:]}\nstderr:\n{result.stderr[-4000:]}")
