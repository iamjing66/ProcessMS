# -*- coding: utf-8 -*-
"""审批流用例：提交→审核→批准→归档全链路、驳回、非法流转、待办、签名。"""
from __future__ import annotations

import asyncio

from tests.helpers import (
    assert_error,
    assert_ok,
    get_approval,
    get_file,
    get_file_logs,
    get_signatures,
    submit_review,
    upload_file,
)


async def test_full_flow_upload_to_archive(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]

    assert result["submitted"]["file_status"] == 2
    assert result["submitted"]["flow_id"] > 0
    assert result["reviewed"]["file_status"] == 3
    assert result["approved"]["file_status"] == 4
    assert result["archived"]["file_status"] == 5
    final = await get_file(client, headers["engineer01"], file_id)
    assert final["file_status"] == 5
    assert final["file_status_text"] == "已归档"
    assert final["current_approver"] is None
    assert "allowed_actions" in final

    # 归档响应带清单快照
    assert result["archived"]["snapshot"]["refresh_type"] == "auto"
    assert result["archived"]["snapshot"]["item_count"] >= 1

    # 文件清单出现该文件
    catalog = assert_ok(await client.get("/api/catalogs?page=1&size=100", headers=headers["admin"]), 200)
    numbers = [item["file_number"] for item in catalog["items"]]
    assert final["file_number"] in numbers
    item = next(item for item in catalog["items"] if item["file_number"] == final["file_number"])
    assert item["file_id"] == file_id
    assert item["version"] == final["version"]
    assert item["download_url"] == f"/api/files/{file_id}/download?version={final['version']}"


async def test_submit_review_assigns_explicit_people(client, headers, seed):
    detail = await upload_file(client, headers["engineer01"], file_name="指定审批人")
    resp = await client.post(
        f"/api/files/{detail['id']}/submit-review",
        headers=headers["engineer01"],
        json={"reviewer_id": seed["user_ids"]["leader01"], "approver_id": seed["user_ids"]["manager01"]},
    )
    body = assert_ok(resp, 200)
    assert body["file_status"] == 2
    assert body["file_status_text"] == "待审核"
    assert body["flow_id"] > 0
    assert body["version"] == detail["version"]
    assert body["reviewer"]["id"] == seed["user_ids"]["leader01"]
    assert body["approver"]["id"] == seed["user_ids"]["manager01"]

    approval = await get_approval(client, headers["engineer01"], detail["id"])
    assert approval["file_id"] == detail["id"]
    flow_data = approval["current_flow"]
    assert flow_data["status"] == 1
    assert flow_data["current_step"] == 1
    steps = flow_data["steps"]
    step1 = next(step for step in steps if step["step_number"] == 1)
    assert step1["step_name"] == "组长审核"
    assert step1["approver"]["id"] == seed["user_ids"]["leader01"]
    assert step1["approval_status"] == 0


async def test_review_pass_creates_approval_step(client, headers, seed, flow):
    detail = await flow.submit(uploader="engineer01")
    body = assert_ok(
        await client.post(
            f"/api/files/{detail['id']}/review",
            headers=headers["leader01"],
            json={"result": "pass", "comment": "工艺参数无误"},
        ),
        200,
    )
    assert body["file_status"] == 3
    assert body["next_approver"]["id"] == seed["user_ids"]["manager01"]

    approval = await get_approval(client, headers["admin"], detail["id"])
    steps = approval["current_flow"]["steps"]
    assert len([step for step in steps if step["step_number"] == 1]) == 1
    step2 = next(step for step in steps if step["step_number"] == 2)
    assert step2["approver"]["id"] == seed["user_ids"]["manager01"]
    assert step2["approval_status"] == 0


async def test_review_reject_returns_draft_and_signature(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]
    flow_id_before = detail.get("flow_id")

    body = assert_ok(
        await client.post(
            f"/api/files/{file_id}/review",
            headers=headers["leader01"],
            json={"result": "reject", "comment": "尺寸标注不清"},
        ),
        200,
    )
    assert body["file_status"] == 1
    assert body["file_status_text"] == "草稿"
    assert body["next_approver"] is None

    current = await get_file(client, headers["engineer01"], file_id)
    assert current["file_status"] == 1
    assert current["current_approver"] is None

    approval = await get_approval(client, headers["admin"], file_id)
    assert approval["current_flow"]["status"] == 0
    assert approval["current_flow"]["reject_reason"] == "尺寸标注不清"

    signatures = await get_signatures(client, headers["engineer01"], file_id)
    assert len(signatures) == 1
    sig = signatures[0]
    assert sig["step_type"] == "review"
    assert sig["step_name"] == "组长审核"
    assert "驳回" in sig["signature_text"]
    assert sig["remark"] == "尺寸标注不清"

    # 驳回后可重新提交，生成新 flow
    again = await submit_review(client, headers["engineer01"], file_id)
    assert again["file_status"] == 2
    if flow_id_before is not None:
        assert again["flow_id"] != flow_id_before


async def test_approve_reject_returns_draft(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]
    assert_ok(
        await client.post(
            f"/api/files/{file_id}/review",
            headers=headers["leader01"],
            json={"result": "pass", "comment": "通过"},
        ),
        200,
    )
    body = assert_ok(
        await client.post(
            f"/api/files/{file_id}/approve",
            headers=headers["manager01"],
            json={"result": "reject", "comment": "工艺参数需复核"},
        ),
        200,
    )
    assert body["file_status"] == 1
    assert body["next_approver"] is None

    approval = await get_approval(client, headers["admin"], file_id)
    assert approval["current_flow"]["status"] == 0

    signatures = await get_signatures(client, headers["engineer01"], file_id)
    assert len(signatures) == 2
    assert {sig["step_type"] for sig in signatures} == {"review", "approve"}
    assert any("驳回" in sig["signature_text"] for sig in signatures)


async def test_review_reject_requires_comment(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["leader01"],
        json={"result": "reject", "comment": ""},
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


async def test_review_invalid_result_value(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["leader01"],
        json={"result": "maybe", "comment": "???"},
    )
    assert_error(resp, 422, "VALIDATION_ERROR")


async def test_review_wrong_state_conflict(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="草稿直接审核")
    resp = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "草稿不能审核"},
    )
    assert_error(resp, 409, "STATE_CONFLICT")


async def test_approve_wrong_state_conflict(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.post(
        f"/api/files/{detail['id']}/approve",
        headers=headers["manager01"],
        json={"result": "pass", "comment": "未审核不能批准"},
    )
    assert_error(resp, 409, "STATE_CONFLICT")


async def test_archive_requires_approved(client, headers):
    detail = await upload_file(client, headers["engineer01"], file_name="草稿直接归档")
    resp = await client.post(
        f"/api/files/{detail['id']}/archive", headers=headers["archivist01"], json={"comment": "直接归档"}
    )
    assert_error(resp, 409, "STATE_CONFLICT")


async def test_duplicate_submit_conflict(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    resp = await client.post(
        f"/api/files/{detail['id']}/submit-review", headers=headers["engineer01"], json={}
    )
    assert_error(resp, 409, "STATE_CONFLICT")


async def test_duplicate_review_after_pass_conflict(client, headers, flow):
    detail = await flow.submit(uploader="engineer01")
    first = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "通过"},
    )
    assert_ok(first, 200)
    second = await client.post(
        f"/api/files/{detail['id']}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "重复审核"},
    )
    assert second.status_code == 409
    assert second.json()["code"] in {"STATE_CONFLICT", "APPROVAL_ALREADY_DONE"}


async def test_pending_lists(client, headers, seed, flow):
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]

    resp = await client.get("/api/approvals/pending?type=review", headers=headers["leader01"])
    body = assert_ok(resp, 200)
    assert body["total"] == 1
    assert body["items"][0]["file"]["id"] == file_id
    assert body["items"][0]["step_number"] == 1
    assert body["items"][0]["approval_status"] == 0
    assert body["items"][0]["initiator"]["id"] == seed["user_ids"]["engineer01"]

    # 待批准阶段前 manager 无待办
    resp = await client.get("/api/approvals/pending?type=approve", headers=headers["manager01"])
    assert assert_ok(resp, 200)["total"] == 0

    assert_ok(
        await client.post(
            f"/api/files/{file_id}/review", headers=headers["leader01"], json={"result": "pass", "comment": "通过"}
        ),
        200,
    )
    resp = await client.get("/api/approvals/pending?type=approve", headers=headers["manager01"])
    approve_items = assert_ok(resp, 200)
    assert approve_items["total"] == 1
    assert approve_items["items"][0]["file"]["id"] == file_id
    assert approve_items["items"][0]["step_number"] == 2

    resp = await client.get("/api/approvals/pending?type=review", headers=headers["leader01"])
    assert assert_ok(resp, 200)["total"] == 0

    # keyword 过滤
    resp = await client.get("/api/approvals/pending?type=approve&keyword=不存在", headers=headers["manager01"])
    assert assert_ok(resp, 200)["total"] == 0


async def test_pending_requires_permission(client, headers):
    resp = await client.get("/api/approvals/pending", headers=headers["engineer01"])
    assert_error(resp, 403, "FORBIDDEN_PERMISSION")


async def test_approval_endpoint_and_flows(client, headers, seed, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]

    approval = await get_approval(client, headers["admin"], file_id)
    current = approval["current_flow"]
    assert current["status"] == 2
    assert current["status_text"] == "已完成"
    assert current["current_step"] == 2
    assert current["version"] == result["file"]["version"]
    assert len(current["steps"]) == 2
    assert all(step["approval_status"] == 1 for step in current["steps"])
    assert current["signatures"]

    flows = assert_ok(
        await client.get(f"/api/approvals/flows?file_id={file_id}", headers=headers["admin"]), 200
    )
    assert flows["total"] >= 1
    first = flows["items"][0]
    assert first["file_id"] == file_id
    assert first["status"] == 2
    assert first["file_number"] == result["file"]["file_number"]

    flow_detail = assert_ok(
        await client.get(f"/api/approvals/flows/{current['id']}", headers=headers["admin"]), 200
    )
    assert flow_detail["id"] == current["id"]
    assert len(flow_detail["steps"]) == 2


async def test_flow_not_found(client, headers):
    resp = await client.get("/api/approvals/flows/999999", headers=headers["admin"])
    assert_error(resp, 404, "FLOW_NOT_FOUND")


async def test_signatures_contract(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    signatures = await get_signatures(client, headers["engineer01"], file_id)
    assert len(signatures) == 2
    assert [sig["step_type"] for sig in signatures] == ["review", "approve"]
    review_sig, approve_sig = signatures
    assert review_sig["step_name"] == "组长审核"
    assert approve_sig["step_name"] == "主管批准"
    assert "审核通过" in review_sig["signature_text"]
    assert "批准通过" in approve_sig["signature_text"]
    assert review_sig["signer_name"] and approve_sig["signer_name"]
    assert review_sig["signer"]["id"] != approve_sig["signer"]["id"]


async def test_allowed_actions_change_with_state(client, headers, seed, flow):
    detail = await upload_file(client, headers["engineer01"], file_name="allowed_actions")
    file_id = detail["id"]
    assert "submit_review" in detail["allowed_actions"]

    await submit_review(
        client,
        headers["engineer01"],
        file_id,
        reviewer_id=seed["user_ids"]["leader01"],
        approver_id=seed["user_ids"]["manager01"],
    )
    pending = await get_file(client, headers["engineer01"], file_id)
    assert "submit_review" not in pending["allowed_actions"]
    # 审核动作属于当前步骤审批人（leader01），工程师本人不应看到 review
    leader_view = await get_file(client, headers["leader01"], file_id)
    assert "review" in leader_view["allowed_actions"]

    await client.post(
        f"/api/files/{file_id}/review", headers=headers["leader01"], json={"result": "pass", "comment": "通过"}
    )
    approved_pending = await get_file(client, headers["manager01"], file_id)
    assert "approve" in approved_pending["allowed_actions"]

    await client.post(
        f"/api/files/{file_id}/approve", headers=headers["manager01"], json={"result": "pass", "comment": "同意"}
    )
    approved = await get_file(client, headers["archivist01"], file_id)
    assert "archive" in approved["allowed_actions"]


async def test_operation_logs_recorded_through_flow(client, headers, flow):
    result = await flow.complete(uploader="engineer01")
    file_id = result["file_id"]
    logs = await get_file_logs(client, headers["admin"], file_id)
    types = [item["operation_type"] for item in logs["items"]]
    for expected in ["upload", "submit_review", "review_pass", "approve_pass", "archive"]:
        assert expected in types, f"缺少操作日志 {expected}，实际={types}"

async def test_concurrent_review_only_one_succeeds(client, headers, flow):
    """并发审核同一文件：仅一个成功，另一个 409（APPROVAL_ALREADY_DONE / STATE_CONFLICT）。"""
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]

    async def do_review():
        return await client.post(
            f"/api/files/{file_id}/review",
            headers=headers["leader01"],
            json={"result": "pass", "comment": "并发审核"},
        )

    first, second = await asyncio.gather(do_review(), do_review())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], f"并发审核期望仅一个成功，实际 {statuses}：{first.text[:200]} / {second.text[:200]}"
    failed = first if first.status_code == 409 else second
    assert failed.json()["code"] == "APPROVAL_ALREADY_DONE"

    final = await get_file(client, headers["engineer01"], file_id)
    assert final["file_status"] == 3


async def test_concurrent_approve_only_one_succeeds(client, headers, flow):
    """并发批准同一文件：仅一个成功，另一个 409。"""
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]
    assert_ok(
        await client.post(
            f"/api/files/{file_id}/review", headers=headers["leader01"], json={"result": "pass", "comment": "通过"}
        ),
        200,
    )

    async def do_approve():
        return await client.post(
            f"/api/files/{file_id}/approve",
            headers=headers["manager01"],
            json={"result": "pass", "comment": "并发批准"},
        )

    first, second = await asyncio.gather(do_approve(), do_approve())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], f"并发批准期望仅一个成功，实际 {statuses}：{first.text[:200]} / {second.text[:200]}"
    failed = first if first.status_code == 409 else second
    assert failed.json()["code"] == "APPROVAL_ALREADY_DONE"

    final = await get_file(client, headers["engineer01"], file_id)
    assert final["file_status"] == 4


async def test_completed_flow_current_approver_null(client, headers, flow):
    """完成态流程：文件 current_approver 与 approval.current_approver 均为 null。"""
    result = await flow.complete(uploader="engineer01")
    assert result["file"]["current_approver"] is None
    assert result["file"]["approval"]["current_approver"] is None
    assert result["file"]["approval"]["status"] == 2


async def test_review_falls_back_when_planned_approver_disabled(client, headers, seed, flow):
    """审核通过时预分配主管已禁用 → 回退自动分配可用主管。"""
    detail = await flow.submit(uploader="engineer01")
    file_id = detail["id"]

    # 禁用预分配的主管
    resp = await client.delete(
        f"/api/users/{seed['user_ids']['manager01']}", headers=headers["admin"]
    )
    assert_ok(resp, 200)

    reviewed = await client.post(
        f"/api/files/{file_id}/review",
        headers=headers["leader01"],
        json={"result": "pass", "comment": "主管已禁用，回退分配"},
    )
    assert_ok(reviewed, 200)
    body = reviewed.json()
    assert body["file_status"] == 3
    assert body["next_approver"] is not None, "预分配主管被禁用后应回退自动分配"
    assert body["next_approver"]["id"] == seed["user_ids"]["admin"]
