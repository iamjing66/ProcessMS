/**
 * 文件详情：元数据、版本历史、审批流程时间线、签名、下载与状态动作
 * 契约：GET /api/files/{id}（FileDetail：allowed_actions/can_download/approval/signatures）
 */
import { api } from "../api.js";
import { can, getCurrentUser, isAdmin } from "../auth.js";
import { escapeHtml, formatDateTime, formatFileSize, statusBadge } from "../format.js";
import { navigate } from "../router.js";
import { confirmDialog, openModal, showError, toast, withButtonLoading } from "../ui.js";
import { setupDropZone, setupProgress, validateFile } from "../upload.js";

/** 流程状态徽标（0 已终止 / 1 进行中 / 2 已完成） */
function flowStatusBadge(status, text) {
  const value = Number(status);
  if (value === 0) return `<span class="badge badge-deleted">${escapeHtml(text || "已终止")}</span>`;
  if (value === 1) return `<span class="badge badge-review">${escapeHtml(text || "进行中")}</span>`;
  if (value === 2) return `<span class="badge badge-approved">${escapeHtml(text || "已完成")}</span>`;
  return `<span class="badge badge-gray">${escapeHtml(text || "未知")}</span>`;
}

export async function render(container, context = {}) {
  const fileId = context.params && context.params.id;
  container.innerHTML = `<div class="loading-state"><span class="spinner"></span><span>正在加载文件详情…</span></div>`;

  let file;
  let versions = [];
  let approval = { currentFlow: null, history: [] };
  let signatures = [];

  try {
    file = await api.getFile(fileId);
  } catch (error) {
    const retry = showError(container, error.message || "文件不存在或无权查看");
    if (retry) {
      retry.addEventListener("click", () => (location.hash === "#/files/" + fileId ? render(container, context) : navigate("/files")));
    }
    return;
  }

  const tasks = [
    api.listVersions(fileId).catch(() => []),
    api.getApproval(fileId).catch(() => ({ currentFlow: null, history: [] })),
  ];
  const [versionList, approvalData] = await Promise.all(tasks);
  versions = versionList || [];
  approval = approvalData || { currentFlow: null, history: [] };
  signatures = Array.isArray(file.signatures) ? file.signatures : [];
  if (!signatures.length) {
    try {
      signatures = await api.listSignatures(fileId);
    } catch (_) {
      signatures = [];
    }
  }

  const actions = renderActions(file);
  container.innerHTML = `
    <div class="detail-head">
      <div class="detail-title-wrap">
        <button type="button" class="btn btn-sm" data-action="back">
          <svg class="icon"><use href="#icon-arrow-left"/></svg><span>返回</span>
        </button>
        <div>
          <div class="detail-title">${escapeHtml(file._name || "未命名文件")}</div>
          <div class="detail-sub">
            <span class="mono">${escapeHtml(file._number || "—")}</span>
            <span>版本 ${escapeHtml(file._version || "—")}</span>
            <span>工序 ${escapeHtml(file._step || "—")}</span>
            ${statusBadge(file.file_status, file.file_status_text)}
          </div>
        </div>
      </div>
      <div class="page-actions">${actions}</div>
    </div>

    <div class="detail-grid">
      <div class="detail-main">
        <div class="card">
          <div class="card-header"><div class="card-title">基本信息</div></div>
          <div class="card-body">
            <div class="meta-grid">${metaHtml(file)}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">版本历史 <span class="count">共 ${versions.length} 个版本</span></div>
          </div>
          <div class="card-body no-pad">${versionsHtml(file, versions)}</div>
        </div>
      </div>

      <div class="detail-side">
        <div class="card">
          <div class="card-header">
            <div class="card-title">审批流程</div>
            ${approval.currentFlow ? flowStatusBadge(approval.currentFlow.status, approval.currentFlow.statusText) : ""}
          </div>
          <div class="card-body">${timelineHtml(approval.currentFlow, file)}</div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">签名信息</div></div>
          <div class="card-body">${signaturesHtml(signatures)}</div>
        </div>
      </div>
    </div>`;

  bindActions(container, context, file, versions);

  // 历史审批流程折叠区
  if (approval.history.length) {
    const body = container.querySelector(".detail-grid .detail-main");
    if (body) {
      const historyCard = document.createElement("div");
      historyCard.className = "card";
      historyCard.innerHTML = `
        <div class="card-header"><div class="card-title">历史审批流程 <span class="count">共 ${approval.history.length} 次</span></div></div>
        <div class="card-body">${approval.history.map((flow) => historyFlowHtml(flow)).join("")}</div>`;
      body.insertBefore(historyCard, body.children[1] || null);
    }
  }
}

/* ---------------- 渲染片段 ---------------- */
function metaHtml(file) {
  const items = [
    { label: "文件编号", value: file._number, mono: true },
    { label: "文件名称", value: file._name },
    { label: "当前版本", value: file._version },
    { label: "工序", value: file._step },
    { label: "工序代码", value: file.process_code || "—" },
    { label: "编制人", value: file._creator || "—" },
    { label: "上传人", value: file._uploader || file._creator || "—" },
    { label: "文件大小", value: formatFileSize(file._size) },
    { label: "初次上传时间", value: formatDateTime(file._createdAt) },
    { label: "最后更新时间", value: formatDateTime(file._updatedAt) },
    {
      label: "当前审批人",
      value:
        (file.current_approver && (file.current_approver.real_name || file.current_approver.username)) ||
        (file.approval && file.approval.current_approver
          ? file.approval.current_approver.real_name || file.approval.current_approver.username
          : "") ||
        "—",
    },
    { label: "备注", value: file._remarks || "—", span: 3 },
  ];
  return items
    .map(
      (item) => `
      <div class="meta-item" style="${item.span ? "grid-column: span " + item.span : ""}">
        <div class="meta-label">${item.label}</div>
        <div class="meta-value ${item.mono ? "mono" : ""}">${escapeHtml(item.value || "—")}</div>
      </div>`
    )
    .join("");
}

function versionsHtml(file, versions) {
  if (!versions.length) {
    return '<div class="timeline-empty" style="padding:18px">暂无版本记录</div>';
  }
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>版本</th><th>变更说明</th><th>上传人</th><th>上传时间</th><th>大小</th><th class="col-actions">操作</th></tr></thead>
        <tbody>
          ${versions
            .map(
              (version) => `
              <tr>
                <td class="mono">${escapeHtml(version.version || "—")}</td>
                <td class="cell-ellipsis" title="${escapeHtml(version._description || "")}">${escapeHtml(version._description || "—")}</td>
                <td>${escapeHtml(version._uploader || "—")}</td>
                <td class="col-num">${formatDateTime(version._time)}</td>
                <td>${formatFileSize(version._size)}</td>
                <td class="col-actions">
                  <button type="button" class="btn-text" data-version-id="${escapeHtml(version.id ?? version.version ?? "")}">下载</button>
                </td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function timelineHtml(flow, file) {
  if (!flow) {
    const summary = file && file.approval;
    if (summary && summary.current_step_name) {
      return `<div class="timeline-empty">当前环节：${escapeHtml(summary.current_step_name)}（${escapeHtml(summary.status_text || "进行中")}）</div>`;
    }
    return '<div class="timeline-empty">暂无审批流程，提交审核后可查看进度。</div>';
  }
  if (!flow.steps.length) return '<div class="timeline-empty">该流程暂无步骤记录</div>';

  return `
    <div class="timeline">
      ${flow.steps
        .map((step) => {
          const statusKey = step.status.key;
          let dotClass = "";
          let dotContent = escapeHtml(String(step.number || "·"));
          if (statusKey === "done") {
            dotClass = "done";
            dotContent = '<svg class="icon"><use href="#icon-check"/></svg>';
          } else if (statusKey === "rejected") {
            dotClass = "rejected";
            dotContent = '<svg class="icon"><use href="#icon-close"/></svg>';
          } else if (Number(flow.status) === 1 && Number(step.number) === Number(flow.currentStep)) {
            dotClass = "current";
          }
          return `
            <div class="timeline-item">
              <div class="timeline-dot ${dotClass}">${dotContent}</div>
              <div class="timeline-main">
                <div class="timeline-head">
                  <span class="timeline-title">${escapeHtml(step.name || "审批环节")}</span>
                  ${step.status ? `<span class="badge ${step.status.cls}">${escapeHtml(step.status.text)}</span>` : ""}
                  <span class="timeline-meta">审批人：${escapeHtml(step.approver || "—")}${step.time ? " · " + formatDateTime(step.time) : ""}</span>
                </div>
                ${step.comment ? `<div class="timeline-comment">${escapeHtml(step.comment)}</div>` : ""}
              </div>
            </div>`;
        })
        .join("")}
    </div>`;
}

function historyFlowHtml(flow) {
  return `
    <details style="margin-bottom:12px">
      <summary style="cursor:pointer;font-size:13px;color:#646a73">
        流程 #${escapeHtml(flow.id ?? "—")} · ${escapeHtml(flow.version || "—")} · ${escapeHtml(flow.statusText || "—")}
        · ${formatDateTime(flow.createdAt)}
        ${flow.rejectReason ? `<span style="color:#f53f3f">（驳回原因：${escapeHtml(flow.rejectReason)}）</span>` : ""}
      </summary>
      <div style="margin-top:8px">${timelineHtml(flow, null)}</div>
    </details>`;
}

function signaturesHtml(signatures) {
  if (!signatures.length) return '<div class="timeline-empty">暂无签名信息</div>';
  return `
    <div class="timeline">
      ${signatures
        .map((signature) => {
          const signer =
            (signature.signer && (signature.signer.real_name || signature.signer.username)) ||
            signature.signer_name ||
            "—";
          return `
            <div class="timeline-item">
              <div class="timeline-dot done"><svg class="icon"><use href="#icon-check"/></svg></div>
              <div class="timeline-main">
                <div class="timeline-head">
                  <span class="timeline-title">${escapeHtml(signature.step_name || "签名")}</span>
                  <span class="timeline-meta">${escapeHtml(signer)}${signature.signed_at ? " · " + formatDateTime(signature.signed_at) : ""}</span>
                </div>
                ${signature.remark ? `<div class="timeline-comment">${escapeHtml(signature.remark)}</div>` : ""}
              </div>
            </div>`;
        })
        .join("")}
    </div>`;
}

/** allowed_actions 决定可用操作；契约保证返回，缺失时按权限兜底 */
function canDo(file, action) {
  if (Array.isArray(file.allowed_actions)) return file.allowed_actions.includes(action);
  const user = getCurrentUser();
  const admin = isAdmin();
  const isOwner = Boolean(user) && (user.id === file._creatorId || user.id === file._uploaderId);
  switch (action) {
    case "update":
      return can("update") && (isOwner || admin);
    case "delete":
      return can("delete") && (isOwner || admin) && ![2, 3].includes(Number(file.file_status));
    case "submit_review":
      return can("update") && (isOwner || admin) && Number(file.file_status) === 1;
    case "review":
      return can("review") && Number(file.file_status) === 2;
    case "approve":
      return can("approve") && Number(file.file_status) === 3;
    case "archive":
      return can("archive") && Number(file.file_status) === 4;
    default:
      return false;
  }
}

function renderActions(file) {
  const buttons = [];
  if (file.can_download !== false) {
    buttons.push('<button type="button" class="btn" data-action="download"><svg class="icon"><use href="#icon-download"/></svg><span>下载</span></button>');
  }
  if (canDo(file, "submit_review")) {
    buttons.push('<button type="button" class="btn btn-primary" data-action="submit_review"><span>提交审核</span></button>');
  }
  if (canDo(file, "review")) {
    buttons.push('<button type="button" class="btn btn-primary" data-action="review"><span>审核</span></button>');
  }
  if (canDo(file, "approve")) {
    buttons.push('<button type="button" class="btn btn-primary" data-action="approve"><span>批准</span></button>');
  }
  if (canDo(file, "update")) {
    buttons.push('<button type="button" class="btn" data-action="update"><span>更新版本</span></button>');
  }
  if (canDo(file, "archive")) {
    buttons.push('<button type="button" class="btn" data-action="archive"><span>归档</span></button>');
  }
  if (canDo(file, "delete")) {
    buttons.push('<button type="button" class="btn btn-danger" data-action="delete"><span>删除</span></button>');
  }
  return buttons.join("");
}

/* ---------------- 事件绑定 ---------------- */
function bindActions(container, context, file, versions) {
  container.querySelector('[data-action="back"]').addEventListener("click", () => navigate("/files"));

  container.querySelectorAll("[data-action]").forEach((button) => {
    const action = button.dataset.action;
    if (!action || action === "back") return;
    button.addEventListener("click", () => {
      if (action === "download") return downloadFile(file);
      if (action === "submit_review") return openSubmitModal(container, context, file);
      if (action === "update") return openUpdateModal(container, context, file);
      if (action === "review" || action === "approve") return openDecisionModal(container, context, file, action);
      if (action === "archive") return openArchiveModal(container, context, file);
      if (action === "delete") return deleteFile(container, context, file);
      return undefined;
    });
  });

  container.querySelectorAll("button[data-version-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const versionId = button.dataset.versionId;
      const version = (versions || []).find((item) => String(item.id ?? item.version) === String(versionId));
      if (!version) {
        toast("未找到该版本信息", "error");
        return;
      }
      button.disabled = true;
      try {
        await api.downloadVersion(file._id, version);
        toast("已开始下载", "success");
      } catch (error) {
        toast(error.message || "版本下载失败", "error");
      } finally {
        button.disabled = false;
      }
    });
  });
}

async function downloadFile(file) {
  try {
    await api.downloadFile(file._id);
    toast("已开始下载", "success");
  } catch (error) {
    toast(error.message || "下载失败", "error");
  }
}

/* ---------------- 动作弹窗 ---------------- */
function openSubmitModal(container, context, file) {
  const modal = openModal({
    title: "提交审核",
    size: "sm",
    content: `
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-tip">提交后文件进入组长审核，审核期间不可编辑；审核人、批准人将由系统按权限自动分配。</div>
        <label class="field">
          <span class="field-label">提交说明</span>
          <textarea class="textarea" name="comment" maxlength="500" placeholder="选填，如：请审核首版工艺"></textarea>
        </label>
      </div>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-primary" data-action="ok">提交审核</button>`,
  });

  modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => modal.close());
  const okButton = modal.footer.querySelector('[data-action="ok"]');
  okButton.addEventListener("click", async () => {
    const comment = modal.body.querySelector('[name="comment"]').value.trim();
    const restore = withButtonLoading(okButton, "提交中…");
    try {
      const data = await api.submitReview(file._id, { comment });
      toast((data && data.message) || "已提交审核", "success");
      modal.close();
      await render(container, context);
    } catch (error) {
      toast(error.message || "提交失败", "error");
      restore();
    }
  });
}

function openUpdateModal(container, context, file) {
  let submitting = false;
  const modal = openModal({
    title: "更新版本",
    size: "md",
    content: `
      <form id="version-form" class="form-grid" autocomplete="off">
        <div class="field span-2">
          <span class="field-label">更新类型</span>
          <div class="radio-group">
            <label class="radio-item"><input type="radio" name="version_type" value="patch" checked><span>补丁修订（默认，末位 +1）</span></label>
            <label class="radio-item"><input type="radio" name="version_type" value="minor"><span>小版本（中位 +1）</span></label>
            <label class="radio-item"><input type="radio" name="version_type" value="major"><span>大版本（首位 +1）</span></label>
          </div>
          ${[4, 5].includes(Number(file.file_status)) ? '<div class="form-tip" style="margin-top:6px">已批准/已归档文件升版后状态回到“草稿”，需重新提交审核。</div>' : ""}
        </div>
        <label class="field span-2">
          <span class="field-label">变更说明<span class="required">*</span></span>
          <textarea class="textarea" name="change_description" maxlength="1000" placeholder="请填写本次变更内容，如：修正页眉尺寸"></textarea>
        </label>
        <div class="field span-2">
          <span class="field-label">新版本文件<span class="required">*</span></span>
          <div class="file-drop" id="version-drop">
            <svg class="icon icon-lg"><use href="#icon-upload"/></svg>
            <div class="file-drop-title">点击选择文件，或将文件拖拽到此处</div>
            <div class="file-drop-sub">支持 PDF / Word / Excel / TXT，单个文件最大 50MB</div>
            <input type="file" id="version-file">
          </div>
          <div id="version-selected"></div>
        </div>
        <div class="field span-2">
          <div class="upload-progress" hidden>
            <div class="progress"><div class="progress-bar"></div></div>
            <div class="progress-text">上传中 0%</div>
          </div>
        </div>
      </form>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-primary" data-action="ok">上传新版本</button>`,
  });

  const form = modal.body.querySelector("#version-form");
  const progress = setupProgress(modal.body);
  const dropZone = setupDropZone(modal.body, {
    dropId: "version-drop",
    inputId: "version-file",
    selectedId: "version-selected",
  });
  const cancelButton = modal.footer.querySelector('[data-action="cancel"]');
  const okButton = modal.footer.querySelector('[data-action="ok"]');

  cancelButton.addEventListener("click", () => {
    if (!submitting) modal.close();
  });

  okButton.addEventListener("click", async () => {
    if (submitting) return;
    const newFile = dropZone.getFile();
    const changeDescription = String(form.elements.change_description.value || "").trim();
    const versionType = form.querySelector('input[name="version_type"]:checked')?.value || "patch";

    if (!newFile) {
      toast("请选择新版本文件", "error");
      return;
    }
    const fileError = validateFile(newFile);
    if (fileError) {
      toast(fileError, "error");
      return;
    }
    if (!changeDescription) {
      toast("请填写变更说明", "error");
      form.elements.change_description.focus();
      return;
    }

    submitting = true;
    const restore = withButtonLoading(okButton, "上传中…");
    cancelButton.disabled = true;
    progress.show();
    try {
      const data = await api.updateFile(
        file._id,
        {
          new_file: newFile,
          version_type: versionType,
          change_description: changeDescription,
        },
        (percent) => progress.update(percent)
      );
      toast((data && data.message) || "新版本上传成功", "success");
      modal.close();
      await render(container, context);
    } catch (error) {
      toast(error.message || "更新失败", "error");
      progress.hide();
      restore();
      cancelButton.disabled = false;
      submitting = false;
    }
  });
}

function openDecisionModal(container, context, file, kind) {
  const isReview = kind === "review";
  const modal = openModal({
    title: isReview ? "审核文件" : "批准文件",
    size: "sm",
    content: `
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-tip">${isReview ? "审核通过后文件进入主管批准环节；驳回则退回草稿。" : "批准通过后文件进入待归档；驳回则退回草稿。"}驳回时审批意见必填。</div>
        <label class="field">
          <span class="field-label">审批意见</span>
          <textarea class="textarea" name="comment" maxlength="500" placeholder="通过时选填，驳回时必填"></textarea>
        </label>
      </div>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-danger" data-action="reject">驳回</button>
      <button type="button" class="btn btn-primary" data-action="pass">通过</button>`,
  });

  const commentEl = modal.body.querySelector('[name="comment"]');
  modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => modal.close());

  async function decide(result) {
    const comment = commentEl.value.trim();
    if (result === "reject" && !comment) {
      toast("驳回时必须填写审批意见", "error");
      commentEl.focus();
      return;
    }
    const buttons = modal.footer.querySelectorAll("button");
    buttons.forEach((button) => (button.disabled = true));
    try {
      const data = isReview
        ? await api.review(file._id, result, comment)
        : await api.approve(file._id, result, comment);
      toast((data && data.message) || "操作成功", "success");
      modal.close();
      await render(container, context);
    } catch (error) {
      toast(error.message || "操作失败", "error");
      buttons.forEach((button) => (button.disabled = false));
    }
  }

  modal.footer.querySelector('[data-action="reject"]').addEventListener("click", () => decide("reject"));
  modal.footer.querySelector('[data-action="pass"]').addEventListener("click", () => decide("pass"));
}

function openArchiveModal(container, context, file) {
  const modal = openModal({
    title: "归档文件",
    size: "sm",
    content: `
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-tip">归档后文件状态变为“已归档”，并自动生成新的文件清单快照。</div>
        <label class="field">
          <span class="field-label">归档说明</span>
          <textarea class="textarea" name="comment" maxlength="500" placeholder="选填，如：资料室归档"></textarea>
        </label>
      </div>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-primary" data-action="ok">确认归档</button>`,
  });

  modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => modal.close());
  const okButton = modal.footer.querySelector('[data-action="ok"]');
  okButton.addEventListener("click", async () => {
    const comment = modal.body.querySelector('[name="comment"]').value.trim();
    const restore = withButtonLoading(okButton, "归档中…");
    try {
      const data = await api.archive(file._id, comment);
      toast((data && data.message) || "归档成功，文件清单已更新", "success");
      modal.close();
      await render(container, context);
    } catch (error) {
      toast(error.message || "归档失败", "error");
      restore();
    }
  });
}

async function deleteFile(container, context, file) {
  const confirmed = await confirmDialog({
    title: "删除文件",
    message: "删除后文件将对所有人不可见（软删除），文件编号不可复用。确定删除吗？",
    okText: "删除",
    danger: true,
  });
  if (!confirmed) return;
  try {
    const data = await api.deleteFile(file._id);
    toast((data && data.message) || "文件已删除", "success");
    navigate("/files");
  } catch (error) {
    toast(error.message || "删除失败", "error");
  }
}
