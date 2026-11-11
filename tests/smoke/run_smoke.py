#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""进程级冒烟脚本：真实启动 uvicorn（SQLite 临时库）后跑完整业务闭环。

用法：
    D:/dsh_workspace/.venv/Scripts/python.exe tests/smoke/run_smoke.py

流程：建库+种子 → 登录 5 个角色 → 上传 → 提交审核 → 组长审核通过
     → 主管批准通过 → 资料员归档 → 查清单 → 下载校验 → 手动刷新 → 统计/日志。
成功退出码 0，失败打印定位信息并退出 1。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SMOKE_PASSWORD = "Smoke@12345"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_env(workdir: Path) -> dict:
    env = os.environ.copy()
    env.update({
        "ENV": "dev",
        "DEBUG": "false",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(workdir / 'smoke.db').as_posix()}",
        "UPLOAD_DIR": str(workdir / "uploads"),
        "SECRET_KEY": "smoke-secret-key-0123456789abcdef0123456789abcdef",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
        "SEED_PASSWORD": SMOKE_PASSWORD,
        "ALLOW_REGISTER": "true",
        "UPLOAD_COOLDOWN_SECONDS": "0",
        "ENABLE_SCHEDULER": "false",
        "CATALOG_REFRESH_ON_STARTUP": "false",
    })
    return env


SEED_SCRIPT = """
import asyncio
from database import init_db, AsyncSessionLocal
from init_data import seed_data

async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_data(session)
        await session.commit()

asyncio.run(main())
"""


def wait_health(client, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                return True
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    print(f"[smoke] 健康检查超时：{last_error}")
    return False


def run() -> int:
    import httpx

    workdir = Path(tempfile.mkdtemp(prefix="processms_smoke_"))
    (workdir / "uploads").mkdir(parents=True, exist_ok=True)
    env = build_env(workdir)

    print(f"[smoke] 工作目录：{workdir}")
    seed = subprocess.run(
        [PYTHON, "-c", SEED_SCRIPT], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120
    )
    if seed.returncode != 0:
        print("[smoke] 种子初始化失败")
        print(seed.stdout[-4000:])
        print(seed.stderr[-4000:])
        return 1

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # trust_env=False：忽略系统 HTTP(S)_PROXY，避免本机代理拦截 127.0.0.1 请求
        with httpx.Client(base_url=base_url, timeout=30.0, trust_env=False) as client:
            if not wait_health(client):
                return 1
            print("[smoke] 服务已启动：/health 正常")

            # 1) 登录全部角色
            tokens = {}
            for username in ["admin", "engineer01", "leader01", "manager01", "archivist01"]:
                resp = client.post("/api/auth/login", json={"username": username, "password": SMOKE_PASSWORD})
                assert resp.status_code == 200, f"登录失败 {username}: {resp.status_code} {resp.text[:300]}"
                tokens[username] = {"Authorization": f"Bearer {resp.json()['access_token']}"}
            print("[smoke] 5 个角色登录成功")

            # 2) 上传（engineer01）
            content = b"%PDF-1.4\nSMOKE-CONTENT\n%%EOF\n"
            resp = client.post(
                "/api/files/upload",
                headers=tokens["engineer01"],
                data={"file_name": "冒烟工艺文件", "process_step": "车削", "process_code": "SM", "remarks": "冒烟"},
                files={"file": ("smoke.pdf", content, "application/pdf")},
            )
            assert resp.status_code == 201, f"上传失败：{resp.status_code} {resp.text[:500]}"
            detail = resp.json()
            file_id = detail["id"]
            file_number = detail["file_number"]
            print(f"[smoke] 上传成功：{file_number}")

            # 3) 提交审核（指定审核/批准人）
            users = client.get("/api/users?keyword=leader01", headers=tokens["admin"]).json()
            leader_id = users["items"][0]["id"]
            users = client.get("/api/users?keyword=manager01", headers=tokens["admin"]).json()
            manager_id = users["items"][0]["id"]
            resp = client.post(
                f"/api/files/{file_id}/submit-review",
                headers=tokens["engineer01"],
                json={"reviewer_id": leader_id, "approver_id": manager_id},
            )
            assert resp.status_code == 200, f"提交审核失败：{resp.status_code} {resp.text[:500]}"
            assert resp.json()["file_status"] == 2

            # 4) 组长审核通过
            resp = client.post(
                f"/api/files/{file_id}/review",
                headers=tokens["leader01"],
                json={"result": "pass", "comment": "冒烟审核通过"},
            )
            assert resp.status_code == 200 and resp.json()["file_status"] == 3, resp.text[:500]

            # 5) 主管批准通过
            resp = client.post(
                f"/api/files/{file_id}/approve",
                headers=tokens["manager01"],
                json={"result": "pass", "comment": "冒烟批准通过"},
            )
            assert resp.status_code == 200 and resp.json()["file_status"] == 4, resp.text[:500]

            # 6) 资料员归档（自动刷新清单）
            resp = client.post(
                f"/api/files/{file_id}/archive",
                headers=tokens["archivist01"],
                json={"comment": "冒烟归档"},
            )
            assert resp.status_code == 200, resp.text[:500]
            archived = resp.json()
            assert archived["file_status"] == 5
            assert archived["snapshot"]["item_count"] >= 1
            print("[smoke] 审批闭环完成：草稿→待审核→待批准→已批准→已归档")

            # 7) 文件清单包含该文件
            catalog = client.get("/api/catalogs?page=1&size=50", headers=tokens["admin"]).json()
            numbers = [item["file_number"] for item in catalog["items"]]
            assert file_number in numbers, f"清单缺少文件：{numbers}"

            # 8) 下载并校验内容
            resp = client.get(f"/api/files/{file_id}/download", headers=tokens["engineer01"])
            assert resp.status_code == 200, f"下载失败：{resp.status_code}"
            assert resp.content == content, "下载内容与上传内容不一致"
            print("[smoke] 清单与下载校验通过")

            # 9) 手动刷新清单 + 统计 + 日志
            resp = client.post("/api/catalogs/refresh", headers=tokens["archivist01"])
            assert resp.status_code == 200, f"手动刷新失败：{resp.status_code} {resp.text[:300]}"
            assert resp.json()["snapshot"]["refresh_type"] == "manual", (
                f"v1.0.3 要求手动刷新生成 manual 快照，实际 {resp.json()['snapshot']}"
            )
            stats = client.get("/api/stats/overview", headers=tokens["admin"]).json()
            assert stats["files"]["by_status"]["archived"] >= 1
            logs = client.get(f"/api/logs?file_id={file_id}&page=1&size=50", headers=tokens["admin"]).json()
            types = {item["operation_type"] for item in logs["items"]}
            assert {"upload", "submit_review", "review_pass", "approve_pass", "archive"} <= types, types
            print("[smoke] 手动刷新/统计/审计日志校验通过")

        print("[smoke] PASS：进程级冒烟全部通过")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        output = ""
        if server.stdout is not None:
            try:
                output = server.stdout.read() or ""
            except Exception:  # noqa: BLE001
                output = ""
        if output.strip():
            tail = output.strip().splitlines()[-40:]
            print("[smoke] uvicorn 输出尾部：\n" + "\n".join(tail))


if __name__ == "__main__":
    try:
        sys.exit(run())
    except AssertionError as exc:
        print(f"[smoke] FAIL：{exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"[smoke] ERROR：{exc}")
        sys.exit(1)
