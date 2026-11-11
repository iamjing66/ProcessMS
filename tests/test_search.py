# -*- coding: utf-8 -*-
"""搜索与分页用例：多条件筛选、日期区间、分页 total、可见性。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest_asyncio

from tests.helpers import assert_error, assert_ok

# (序号, 名称, 工序, 工序代码, 编制人, 状态, 首次上传时间)
BULK_FILES = [
    (1, "车削工艺A", "车削", "SR", "engineer01", 5, datetime(2026, 1, 5, 2, 0, 0)),
    (2, "车削工艺B", "车削", "SR", "engineer01", 4, datetime(2026, 1, 6, 3, 0, 0)),
    (3, "铣削工艺C", "铣削", "MI", "engineer02", 5, datetime(2026, 2, 10, 4, 0, 0)),
    (4, "装配工艺D", "装配", "ZP", "engineer01", 1, datetime(2026, 2, 10, 5, 0, 0)),
    (5, "装配工艺E", "装配", "ZP", "engineer02", 1, datetime(2026, 3, 20, 6, 0, 0)),
    (6, "焊接工艺F", "焊接", "HJ", "leader01", 3, datetime(2026, 1, 6, 7, 0, 0)),
    (7, "车削工艺G", "车削", "SR", "engineer02", 5, datetime(2026, 3, 20, 8, 0, 0)),
    (8, "检验工艺H", "检验", "JY", "engineer01", 4, datetime(2026, 2, 11, 9, 0, 0)),
    (9, "包装工艺I", "包装", "BZ", "manager01", 5, datetime(2026, 1, 5, 10, 0, 0)),
    (10, "磨削工艺J", "磨削", "MJ", "engineer01", 1, datetime(2026, 3, 20, 11, 0, 0)),
    (11, "热处理工艺K", "热处理", "RC", "archivist01", 5, datetime(2026, 2, 10, 12, 0, 0)),
    (12, "已删除工艺L", "车削", "SR", "engineer01", 0, datetime(2026, 1, 7, 13, 0, 0)),
]

NON_DELETED = [item for item in BULK_FILES if item[5] != 0]


@pytest_asyncio.fixture
async def bulk_files(seed, db_session):
    """直接向测试库写入 12 条不同维度文件，避免受上传限流影响。"""
    from models.file import ProcessFile

    for seq, name, step, code, creator, status, uploaded_at in BULK_FILES:
        period = uploaded_at.strftime("%Y%m")
        row = ProcessFile(
            file_number=f"{code}-{period}-{seq:04d}",
            file_name=name,
            file_type=".pdf",
            process_code=code,
            process_step=step,
            version="V1.0.0",
            uploader_id=seed["user_ids"][creator],
            creator_id=seed["user_ids"][creator],
            initial_upload_time=uploaded_at,
            last_update_time=uploaded_at,
            file_size=1024 * seq,
            storage_path=f"2026/{uploaded_at.month:02d}/bulk_{seq}.pdf",
            file_status=status,
        )
        db_session.add(row)
    await db_session.commit()
    return NON_DELETED


async def test_list_all_visible_as_admin(client, headers, bulk_files):
    resp = await client.get("/api/files?page=1&size=100", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["total"] == len(NON_DELETED) == 11
    assert body["pages"] == 1
    ids = {item["id"] for item in body["items"]}
    assert len(ids) == 11


async def test_keyword_matches_name_number_step_creator(client, headers, bulk_files):
    resp = await client.get("/api/files?keyword=车削&page=1&size=100", headers=headers["admin"])
    body = assert_ok(resp, 200)
    names = {item["file_name"] for item in body["items"]}
    assert names == {"车削工艺A", "车削工艺B", "车削工艺G"}
    assert body["total"] == 3

    resp = await client.get("/api/files?file_number=SR-202601&page=1&size=100", headers=headers["admin"])
    body = assert_ok(resp, 200)
    assert body["total"] == 2  # 已删除的 L 不计入


async def test_filter_by_name_step_code(client, headers, bulk_files):
    body = assert_ok(await client.get("/api/files?file_name=工艺C&page=1&size=100", headers=headers["admin"]), 200)
    assert [item["file_name"] for item in body["items"]] == ["铣削工艺C"]

    body = assert_ok(await client.get("/api/files?process_step=装配&page=1&size=100", headers=headers["admin"]), 200)
    assert {item["file_name"] for item in body["items"]} == {"装配工艺D", "装配工艺E"}

    body = assert_ok(await client.get("/api/files?process_code=MI&page=1&size=100", headers=headers["admin"]), 200)
    assert [item["file_name"] for item in body["items"]] == ["铣削工艺C"]


async def test_filter_by_creator_id_and_name(client, headers, seed, bulk_files):
    body = assert_ok(
        await client.get(
            f"/api/files?creator_id={seed['user_ids']['engineer02']}&page=1&size=100", headers=headers["admin"]
        ),
        200,
    )
    assert {item["file_name"] for item in body["items"]} == {"铣削工艺C", "装配工艺E", "车削工艺G"}

    me = assert_ok(await client.get("/api/auth/me", headers=headers["engineer01"]), 200)
    body = assert_ok(
        await client.get(f"/api/files?creator_name={me['real_name']}&page=1&size=100", headers=headers["admin"]),
        200,
    )
    assert body["total"] >= 4
    assert all(item["creator"]["id"] == seed["user_ids"]["engineer01"] for item in body["items"])


async def test_filter_by_status(client, headers, bulk_files):
    body = assert_ok(await client.get("/api/files?status=4,5&page=1&size=100", headers=headers["admin"]), 200)
    assert body["total"] == 7
    assert all(item["file_status"] in (4, 5) for item in body["items"])


async def test_filter_by_upload_date_range_inclusive(client, headers, bulk_files):
    body = assert_ok(
        await client.get(
            "/api/files?upload_date_start=2026-02-10&upload_date_end=2026-02-10&page=1&size=100",
            headers=headers["admin"],
        ),
        200,
    )
    assert {item["file_name"] for item in body["items"]} == {"铣削工艺C", "装配工艺D", "热处理工艺K"}

    body = assert_ok(
        await client.get(
            "/api/files?upload_date_start=2026-01-01&upload_date_end=2026-01-31&page=1&size=100",
            headers=headers["admin"],
        ),
        200,
    )
    assert {item["file_name"] for item in body["items"]} == {
        "车削工艺A", "车削工艺B", "焊接工艺F", "包装工艺I",
    }


async def test_pagination_total_pages_and_bounds(client, headers, bulk_files):
    body = assert_ok(await client.get("/api/files?page=1&size=5", headers=headers["admin"]), 200)
    assert body["total"] == 11
    assert body["pages"] == 3
    assert len(body["items"]) == 5

    page3 = assert_ok(await client.get("/api/files?page=3&size=5", headers=headers["admin"]), 200)
    assert len(page3["items"]) == 1

    beyond = assert_ok(await client.get("/api/files?page=9&size=5", headers=headers["admin"]), 200)
    assert beyond["items"] == []
    assert beyond["total"] == 11

    # size 越界钳制并回显
    clamped = assert_ok(await client.get("/api/files?page=1&size=1000", headers=headers["admin"]), 200)
    assert clamped["size"] == 100
    tiny = assert_ok(await client.get("/api/files?page=1&size=0", headers=headers["admin"]), 200)
    assert tiny["size"] == 1


async def test_invalid_sort_rejected(client, headers, bulk_files):
    resp = await client.get("/api/files?sort=not_a_column", headers=headers["admin"])
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_sort_by_file_number(client, headers, bulk_files):
    body = assert_ok(await client.get("/api/files?sort=file_number&order=asc&page=1&size=100", headers=headers["admin"]), 200)
    numbers = [item["file_number"] for item in body["items"]]
    assert numbers == sorted(numbers)


async def test_keyword_like_escape(client, headers, bulk_files):
    """输入 % 不应被当作通配符匹配全部文件。"""
    body = assert_ok(await client.get("/api/files?keyword=%25&page=1&size=100", headers=headers["admin"]), 200)
    assert body["total"] == 0


async def test_visibility_for_engineer(client, headers, seed, bulk_files):
    """engineer01 只能看到：本人创建的 或 已批准/已归档（4/5）的文件。"""
    body = assert_ok(await client.get("/api/files?page=1&size=100", headers=headers["engineer01"]), 200)
    names = {item["file_name"] for item in body["items"]}
    expected = {
        "车削工艺A", "车削工艺B", "铣削工艺C", "装配工艺D", "车削工艺G",
        "检验工艺H", "包装工艺I", "磨削工艺J", "热处理工艺K",
    }
    assert names == expected
    # engineer02 的草稿 E、leader01 的审批中 F 不可见
    assert "装配工艺E" not in names
    assert "焊接工艺F" not in names
    assert "已删除工艺L" not in names


async def test_search_combined_filters(client, headers, bulk_files):
    body = assert_ok(
        await client.get(
            "/api/files?process_step=车削&status=5&page=1&size=100", headers=headers["admin"]
        ),
        200,
    )
    assert {item["file_name"] for item in body["items"]} == {"车削工艺A", "车削工艺G"}

async def test_upload_date_filter_uses_business_timezone(client, headers):
    """日期筛选按业务时区（Asia/Shanghai）解释；用业务日而非 UTC 日。"""
    from tests.helpers import upload_file

    detail = await upload_file(client, headers["engineer01"], file_name="业务日筛选文件")
    business_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    body = assert_ok(
        await client.get(
            f"/api/files?upload_date_start={business_date}&upload_date_end={business_date}&keyword=业务日筛选文件",
            headers=headers["engineer01"],
        ),
        200,
    )
    ids = [item["id"] for item in body["items"]]
    assert detail["id"] in ids, f"业务日 {business_date} 过滤结果缺少新上传文件：{body}"

    # 响应时间仍为 UTC ISO8601，转换到业务时区后日期与筛选日一致
    from datetime import datetime as dt

    uploaded = dt.fromisoformat(body["items"][0]["initial_upload_time"])
    assert uploaded.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() == business_date
