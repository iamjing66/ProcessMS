# -*- coding: utf-8 -*-
"""上传用例：编号、类型/大小校验、落盘、并发唯一。"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import get_settings
from tests.helpers import DEFAULT_PDF, assert_error, assert_ok, upload_file


def _period() -> str:
    """编号中的 YYYYMM 使用 Asia/Shanghai 业务时区的当前年月。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m")


async def test_upload_success_contract(client, headers, seed):
    detail = await upload_file(
        client,
        headers["engineer01"],
        file_name="主轴加工工艺",
        process_step="车削",
        process_code="CN",
        remarks="首版",
    )
    assert detail["file_status"] == 1
    assert detail["file_status_text"] == "草稿"
    assert detail["file_name"] == "主轴加工工艺"
    assert detail["process_step"] == "车削"
    assert detail["process_code"] == "CN"
    assert detail["version"] == "V1.0.0"
    assert re.fullmatch(r"CN-\d{6}-\d{4}", detail["file_number"]), detail["file_number"]
    assert detail["file_number"].split("-")[1] == _period()
    assert detail["file_type"].lower() == ".pdf"
    assert detail["creator"]["id"] == seed["user_ids"]["engineer01"]
    assert detail["uploader"]["id"] == seed["user_ids"]["engineer01"]
    assert detail["version_count"] == 1
    assert "submit_review" in detail["allowed_actions"]


async def test_upload_default_process_code(client, headers):
    detail = await upload_file(
        client, headers["engineer01"], file_name="通用工序文件", process_step="通用", process_code=None
    )
    assert detail["process_code"] == "GEN"
    assert detail["file_number"].startswith("GEN-")


async def test_upload_rejects_bad_extension(client, headers):
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "恶意程序", "process_step": "车削", "process_code": "CN"},
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert_error(resp, 400, "FILE_TYPE_NOT_ALLOWED")


async def test_upload_size_limit(client, headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_FILE_SIZE", 32, raising=False)
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "超大文件", "process_step": "车削", "process_code": "CN"},
        files={"file": ("big.pdf", DEFAULT_PDF + b"x" * 256, "application/pdf")},
    )
    assert_error(resp, 413, "FILE_SIZE_EXCEEDED")

    listing = assert_ok(await client.get("/api/files?page=1&size=100", headers=headers["admin"]), 200)
    assert all(item["file_name"] != "超大文件" for item in listing["items"])


async def test_upload_duplicate_name_same_process(client, headers):
    await upload_file(client, headers["engineer01"], file_name="重复名称文件", process_code="CN")
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer02"],
        data={"file_name": "重复名称文件", "process_step": "车削", "process_code": "CN"},
        files={"file": ("same.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 409, "FILE_NAME_DUPLICATED")


async def test_upload_number_increments_and_unique(client, headers):
    first = await upload_file(client, headers["engineer01"], file_name="编号测试1", process_code="WE")
    second = await upload_file(client, headers["engineer02"], file_name="编号测试2", process_code="WE")
    assert first["file_number"] != second["file_number"]
    seq1 = int(first["file_number"].split("-")[-1])
    seq2 = int(second["file_number"].split("-")[-1])
    assert seq2 == seq1 + 1


async def test_upload_invalid_version_format(client, headers):
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "版本格式错误", "process_step": "车削", "version": "1.0"},
        files={"file": ("v.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 400, "VERSION_FORMAT_INVALID")


async def test_upload_invalid_process_code(client, headers):
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "工序代码错误", "process_step": "车削", "process_code": "车削工序"},
        files={"file": ("p.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_upload_missing_file_field(client, headers):
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "没有文件", "process_step": "车削"},
    )
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_upload_requires_auth(client):
    resp = await client.post(
        "/api/files/upload",
        data={"file_name": "匿名", "process_step": "车削"},
        files={"file": ("a.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 401, "AUTH_REQUIRED")


async def test_upload_stores_file_on_disk(client, headers, db_session, upload_dir):
    from sqlalchemy import select

    from models.file import ProcessFile

    detail = await upload_file(client, headers["engineer01"], file_name="落盘检查")
    row = (await db_session.execute(select(ProcessFile).where(ProcessFile.id == detail["id"]))).scalar_one()

    stored = Path(row.storage_path)
    if not stored.is_absolute():
        stored = Path(upload_dir) / row.storage_path
    assert stored.exists(), f"落盘文件不存在：{stored}"
    assert stored.stat().st_size > 0
    # 不允许把客户端文件名直接拼进路径（防目录穿越）
    assert "落盘检查" not in row.storage_path


async def test_upload_rate_limit(client, headers, monkeypatch):
    """同用户 2 秒冷却：连续两次上传第二次 429。"""
    monkeypatch.setattr(get_settings(), "UPLOAD_COOLDOWN_SECONDS", 2, raising=False)
    await upload_file(client, headers["engineer01"], file_name="限流第一次", process_code="CN")
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "限流第二次", "process_step": "车削", "process_code": "CN"},
        files={"file": ("second.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 429, "RATE_LIMITED")


@pytest.mark.slow
async def test_concurrent_uploads_unique_numbers(client, headers, monkeypatch):
    """并发上传（3 个用户各 3 次）编号必须唯一。"""
    monkeypatch.setattr(get_settings(), "UPLOAD_COOLDOWN_SECONDS", 0, raising=False)
    uploaders = ["admin", "engineer01", "engineer02"]

    async def one(index: int):
        username = uploaders[index % len(uploaders)]
        resp = await client.post(
            "/api/files/upload",
            headers=headers[username],
            data={
                "file_name": f"并发文件{index}",
                "process_step": "车削",
                "process_code": "CC",
            },
            files={"file": (f"c{index}.pdf", DEFAULT_PDF, "application/pdf")},
        )
        return resp

    responses = await asyncio.gather(*[one(i) for i in range(9)])
    ok_numbers = []
    for resp in responses:
        if resp.status_code == 201:
            ok_numbers.append(resp.json()["file_number"])
        else:
            assert resp.status_code in (409, 429), f"并发上传异常：{resp.status_code} {resp.text[:300]}"
    assert len(ok_numbers) == len(set(ok_numbers)), "并发上传出现重复编号"
    assert len(ok_numbers) >= 3

async def test_duplicate_name_reusable_after_soft_delete(client, headers):
    """软删除后同工序同名可重新上传（删除态不参与重名校验）。"""
    first = await upload_file(client, headers["engineer01"], file_name="可复用名称", process_code="CN")
    assert_ok(await client.delete(f"/api/files/{first['id']}", headers=headers["engineer01"]), 200)
    second = await upload_file(client, headers["engineer01"], file_name="可复用名称", process_code="CN")
    assert second["file_status"] == 1
    assert second["file_number"] != first["file_number"]


async def test_rename_to_existing_name_rejected(client, headers):
    """更新改名与同工序已有文件重名 → 409 FILE_NAME_DUPLICATED。"""
    from tests.helpers import update_file

    first = await upload_file(client, headers["engineer01"], file_name="改名甲", process_code="CN")
    await upload_file(client, headers["engineer01"], file_name="改名乙", process_code="CN")

    resp = await client.put(
        f"/api/files/{first['id']}",
        headers=headers["engineer01"],
        data={"file_name": "改名乙"},
    )
    assert_error(resp, 409, "FILE_NAME_DUPLICATED")


async def test_upload_rejects_empty_file(client, headers):
    """0 字节空文件拒绝（API v1.0.3：400 FILE_EMPTY）。"""
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer01"],
        data={"file_name": "空文件", "process_step": "车削", "process_code": "CN"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert_error(resp, 400, "FILE_EMPTY")


async def test_duplicate_name_normalized_whitespace(client, headers):
    """重名比较忽略首尾空白与连续空白。"""
    await upload_file(client, headers["engineer01"], file_name="壳体 加工", process_code="CN")
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer02"],
        data={"file_name": "  壳体  加工  ", "process_step": "车削", "process_code": "CN"},
        files={"file": ("dup.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 409, "FILE_NAME_DUPLICATED")


async def test_duplicate_name_case_insensitive(client, headers):
    """重名比较对英文大小写不敏感。"""
    await upload_file(client, headers["engineer01"], file_name="PDF Guide", process_code="CN")
    resp = await client.post(
        "/api/files/upload",
        headers=headers["engineer02"],
        data={"file_name": "pdf  guide", "process_step": "车削", "process_code": "CN"},
        files={"file": ("dup2.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 409, "FILE_NAME_DUPLICATED")


async def test_upload_chinese_filename_roundtrip(client, headers):
    """中文原始文件名上传后下载内容一致（落盘用 UUID，不拼客户端文件名）。"""
    from tests.helpers import download

    content = b"%PDF-1.4\nCHINESE-NAME\n"
    detail = await upload_file(
        client, headers["engineer01"], filename="工艺图纸.pdf", file_name="中文文件名工艺", content=content
    )
    assert detail["file_type"] == ".pdf"
    resp = await download(client, headers["engineer01"], detail["id"])
    assert resp.content == content
