# -*- coding: utf-8 -*-
"""版本用例：升版规则、审核中锁定、版本历史与版本下载。"""
from __future__ import annotations

from tests.helpers import (
    DEFAULT_PDF,
    assert_error,
    assert_ok,
    download,
    get_file,
    get_versions,
    update_file,
    upload_file,
)


async def test_patch_version_increment(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="版本patch")
    updated = await update_file(
        client,
        headers["engineer01"],
        detail["id"],
        new_file=True,
        content=DEFAULT_PDF + b"patch",
        version_type="patch",
        change_description="修正错别字",
    )
    assert updated["version"] == "V1.0.1"
    assert updated["file_status"] == 1
    assert updated["version_count"] == 2


async def test_minor_version_increment(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="版本minor")
    updated = await update_file(
        client, headers["engineer01"], detail["id"], new_file=True, version_type="minor"
    )
    assert updated["version"] == "V1.1.0"


async def test_major_version_increment(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="版本major")
    updated = await update_file(
        client, headers["engineer01"], detail["id"], new_file=True, version_type="major"
    )
    assert updated["version"] == "V2.0.0"


async def test_metadata_update_keeps_version(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="元数据更新")
    updated = await update_file(
        client, headers["engineer01"], detail["id"], file_name="元数据更新改名", remarks="只改元数据"
    )
    assert updated["file_name"] == "元数据更新改名"
    assert updated["version"] == detail["version"]
    assert updated["version_count"] == 1
    assert updated["file_number"] == detail["file_number"]


async def test_update_locked_during_review(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.put(
        f"/api/files/{detail['id']}",
        headers=headers["engineer01"],
        data={"remarks": "审核中改备注"},
    )
    assert_error(resp, 409, "FILE_LOCKED")


async def test_update_locked_during_approval(client, headers, seed, flow):
    """审核通过进入待批准后仍锁定。"""
    detail = await flow.submit(uploader="engineer01")
    assert_ok(
        await client.post(
            f"/api/files/{detail['id']}/review",
            headers=headers["leader01"],
            json={"result": "pass", "comment": "通过"},
        ),
        200,
    )
    resp = await client.put(
        f"/api/files/{detail['id']}",
        headers=headers["engineer01"],
        data={"remarks": "待批准时改备注"},
    )
    assert_error(resp, 409, "FILE_LOCKED")


async def test_approved_file_requires_new_file(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    assert result["file"]["file_status"] == 5

    resp = await client.put(
        f"/api/files/{file_id}", headers=headers["engineer01"], data={"remarks": "只改备注"}
    )
    assert_error(resp, 400, "NEW_FILE_REQUIRED")


async def test_archived_file_update_with_new_file_returns_draft(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    old_version = result["file"]["version"]

    updated = await update_file(
        client, headers["engineer01"], file_id, new_file=True, version_type="major", change_description="大改"
    )
    assert updated["file_status"] == 1
    assert updated["version"] == "V2.0.0"
    assert old_version == "V1.0.0"


async def test_version_history_contract(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="版本历史")
    file_id = detail["id"]
    await update_file(
        client, headers["engineer01"], file_id, new_file=True, version_type="minor", change_description="升小版本"
    )

    versions = await get_versions(client, headers["engineer01"], file_id)
    assert len(versions) == 2
    assert [item["version"] for item in versions] == ["V1.1.0", "V1.0.0"]
    latest = versions[0]
    for field in ["id", "file_id", "version", "file_size", "file_hash", "upload_time", "download_url", "uploader"]:
        assert field in latest, f"版本项缺少字段 {field}: {latest}"
    assert latest["change_description"] == "升小版本"
    assert latest["download_url"].endswith("?version=V1.1.0")
    assert latest["file_hash"]


async def test_change_description_default_when_empty(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="空变更说明")
    await update_file(client, headers["engineer01"], detail["id"], new_file=True, version_type="patch")
    versions = await get_versions(client, headers["engineer01"], detail["id"])
    assert versions[0]["change_description"] == "未填写"


async def test_version_download_specific_and_current(client, headers):
    first_content = b"%PDF-1.4\nFIRST-VERSION\n"
    second_content = b"%PDF-1.4\nSECOND-VERSION\n"
    detail = await upload_file(client, headers["engineer01"], file_name="版本下载", content=first_content)
    file_id = detail["id"]
    await update_file(
        client, headers["engineer01"], file_id, new_file=True, content=second_content, version_type="patch"
    )

    current = await download(client, headers["engineer01"], file_id)
    assert current.content == second_content

    old = await download(client, headers["engineer01"], file_id, version="V1.0.0")
    assert old.content == first_content

    dedicated = await client.get(
        f"/api/files/{file_id}/versions/V1.0.0/download", headers=headers["engineer01"]
    )
    assert dedicated.status_code == 200
    assert dedicated.content == first_content


async def test_download_unknown_version(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="不存在版本")
    resp = await client.get(
        f"/api/files/{detail['id']}/download", headers=headers["engineer01"], params={"version": "V9.9.9"}
    )
    assert_error(resp, 404, "VERSION_NOT_FOUND")


async def test_invalid_version_type(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="非法版本类型")
    resp = await client.put(
        f"/api/files/{detail['id']}",
        headers=headers["engineer01"],
        data={"version_type": "super"},
        files={"new_file": ("v.pdf", DEFAULT_PDF, "application/pdf")},
    )
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_process_code_change_only_draft(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="改工序代码", process_code="CN")
    updated = await update_file(client, headers["engineer01"], detail["id"], process_code="MI")
    assert updated["process_code"] == "MI"
    # 编号生成后不可变
    assert updated["file_number"] == detail["file_number"]
