/**
 * 文件管理：列表 + 多条件检索 + 分页 + 上传（进度/防重复）+ 行操作
 */
import { api } from "../api.js";
import { can, getCurrentUser, isAdmin } from "../auth.js";
import { DEFAULT_PAGE_SIZE } from "../config.js";
import { escapeHtml, formatDateTime, statusBadge } from "../format.js";
import { navigate } from "../router.js";
import {
  bindPagination,
  confirmDialog,
  openModal,
  paginationHtml,
  showEmpty,
  showError,
  showLoading,
  toast,
  withButtonLoading,
} from "../ui.js";
import { setupDropZone, setupProgress, validateFile } from "../upload.js";

const FILTER_KEYS = [
  "file_name",
  "file_number",
  "creator_name",
  "process_step",
  "status",
  "upload_date_start",
  "upload_date_end",
];

const state = {
  page: 1,
  size: DEFAULT_PAGE_SIZE,
  filters: Object.fromEntries(FILTER_KEYS.map((key) => [key, ""])),
};

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "1", label: "草稿" },
  { value: "2", label: "待审核" },
  { value: "3", label: "待批准" },
  { value: "4", label: "已批准" },
  { value: "5", label: "已归档" },
];

export async function render(container, context = {}) {
  const statusOptions = STATUS_OPTIONS.map(
    (item) => `<option value="${item.value}" ${state.filters.status === item.value ? "selected" : ""}>${item.label}</option>`
  ).join("");

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>文件管理</h2>
        <p class="page-desc">上传、检索工艺文件，并跟踪版本与审批状态</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn btn-primary" id="btn-upload">
          <svg class="icon"><use href="#icon-upload"/></svg><span>上传文件</span>
        </button>
      </div>
    </div>

    <div class="card">
      <form class="filter-form" id="file-filter" autocomplete="off">
        <div class="filter-field">
          <span class="field-label">文件名称</span>
          <input class="input" name="file_name" maxlength="255" placeholder="模糊匹配" value="${escapeHtml(state.filters.file_name)}">
        </div>
        <div class="filter-field">
          <span class="field-label">文件编号</span>
          <input class="input" name="file_number" maxlength="50" placeholder="如 CN-202611-0001" value="${escapeHtml(state.filters.file_number)}">
        </div>
        <div class="filter-field">
          <span class="field-label">编制人</span>
          <input class="input" name="creator_name" maxlength="50" placeholder="姓名模糊匹配" value="${escapeHtml(state.filters.creator_name)}">
        </div>
        <div class="filter-field">
          <span class="field-label">工序</span>
          <input class="input" name="process_step" maxlength="100" placeholder="如 车削" value="${escapeHtml(state.filters.process_step)}">
        </div>
        <div class="filter-field">
          <span class="field-label">状态</span>
          <select class="select" name="status">${statusOptions}</select>
        </div>
        <div class="filter-field wide">
          <span class="field-label">上传日期</span>
          <div class="date-range">
            <input type="date" class="input" name="upload_date_start" value="${escapeHtml(state.filters.upload_date_start)}">
            <span class="sep">至</span>
            <input type="date" class="input" name="upload_date_end" value="${escapeHtml(state.filters.upload_date_end)}">
          </div>
        </div>
        <div class="filter-actions">
          <button type="submit" class="btn btn-primary">
            <svg class="icon"><use href="#icon-search"/></svg><span>查询</span>
          </button>
          <button type="button" class="btn" id="btn-reset-filter">重置</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">文件列表 <span class="count" id="file-count"></span></div>
        <div class="card-actions">
          <button type="button" class="btn btn-sm" id="btn-refresh-files">
            <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新</span>
          </button>
        </div>
      </div>
      <div id="file-table-area"></div>
    </div>`;

  const form = container.querySelector("#file-filter");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    FILTER_KEYS.forEach((key) => {
      state.filters[key] = String(formData.get(key) || "").trim();
    });
    state.page = 1;
    loadFiles(container);
  });

  container.querySelector("#btn-reset-filter").addEventListener("click", () => {
    FILTER_KEYS.forEach((key) => {
      state.filters[key] = "";
    });
    form.querySelectorAll("input, select").forEach((field) => {
      field.value = "";
    });
    state.page = 1;
    loadFiles(container);
  });

  container.querySelector("#btn-refresh-files").addEventListener("click", () => loadFiles(container));
  container.querySelector("#btn-upload").addEventListener("click", () => openUploadModal(container));

  await loadFiles(container);
}

/* ---------------- 列表加载与渲染 ---------------- */
async function loadFiles(container) {
  const area = container.querySelector("#file-table-area");
  if (!area) return;
  showLoading(area);
  const params = { page: state.page, size: state.size };
  FILTER_KEYS.forEach((key) => {
    if (state.filters[key]) params[key] = state.filters[key];
  });

  try {
    const result = await api.listFiles(params);
    state.page = result.page || 1;
    state.size = result.size || state.size;
    const countEl = container.querySelector("#file-count");
    if (countEl) countEl.textContent = `共 ${result.total} 个`;
    renderTable(area, result, container);
  } catch (error) {
    const retry = showError(area, error.message || "文件列表加载失败");
    retry.addEventListener("click", () => loadFiles(container));
  }
}

function renderTable(area, result, container) {
  if (!result.items.length) {
    const hasFilter = FILTER_KEYS.some((key) => state.filters[key]);
    showEmpty(
      area,
      hasFilter ? "未找到匹配的文件" : "暂无文件",
      hasFilter ? "请调整筛选条件后重试" : "点击右上角“上传文件”新建工艺文件"
    );
    return;
  }

  const user = getCurrentUser();
  const admin = isAdmin();
  area.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>文件编号</th>
            <th>文件名称</th>
            <th>版本</th>
            <th>工序</th>
            <th>编制人</th>
            <th>状态</th>
            <th>更新时间</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>${result.items.map((file) => rowHtml(file, user, admin)).join("")}</tbody>
      </table>
    </div>
    ${paginationHtml(result)}`;

  bindPagination(area, ({ page, size }) => {
    if (size) {
      state.size = size;
      state.page = 1;
    } else {
      state.page = page;
    }
    loadFiles(container);
  });

  const tbody = area.querySelector("tbody");
  if (tbody) tbody.addEventListener("click", (event) => handleRowAction(event, container));
}

function rowHtml(file, user, admin) {
  const isOwner = Boolean(user) && (user.id === file._creatorId || user.id === file._uploaderId);
  const allowOwner = isOwner || admin;
  const status = Number(file.file_status);
  const canSubmit = can("update") && allowOwner && status === 1;
  const canDelete = can("delete") && allowOwner && status !== 2 && status !== 3;

  const actions = [
    `<button type="button" class="btn-text" data-action="detail" data-id="${escapeHtml(file._id)}">详情</button>`,
    `<button type="button" class="btn-text" data-action="download" data-id="${escapeHtml(file._id)}">下载</button>`,
    canSubmit
      ? `<button type="button" class="btn-text" data-action="submit" data-id="${escapeHtml(file._id)}">提交审核</button>`
      : "",
    canDelete
      ? `<button type="button" class="btn-text danger" data-action="delete" data-id="${escapeHtml(file._id)}">删除</button>`
      : "",
  ]
    .filter(Boolean)
    .join("");

  return `
    <tr>
      <td class="mono">${escapeHtml(file._number || "—")}</td>
      <td class="cell-name cell-ellipsis" title="${escapeHtml(file._name || "")}">${escapeHtml(file._name || "—")}</td>
      <td>${escapeHtml(file._version || "—")}</td>
      <td>${escapeHtml(file._step || "—")}</td>
      <td>${escapeHtml(file._creator || "—")}</td>
      <td>${statusBadge(file.file_status, file.file_status_text)}</td>
      <td class="col-num">${formatDateTime(file._updatedAt)}</td>
      <td class="col-actions">${actions}</td>
    </tr>`;
}

async function handleRowAction(event, container) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const fileId = button.dataset.id;
  const action = button.dataset.action;

  if (action === "detail") {
    navigate("/files/" + fileId);
    return;
  }

  if (action === "download") {
    button.disabled = true;
    try {
      await api.downloadFile(fileId);
      toast("已开始下载", "success");
    } catch (error) {
      toast(error.message || "下载失败", "error");
    } finally {
      button.disabled = false;
    }
    return;
  }

  if (action === "submit") {
    const confirmed = await confirmDialog({
      title: "提交审核",
      message: "提交后文件将进入组长审核，审核期间不可编辑。确定提交吗？",
      okText: "提交审核",
    });
    if (!confirmed) return;
    button.disabled = true;
    try {
      const data = await api.submitReview(fileId, {});
      toast((data && data.message) || "已提交审核", "success");
      await loadFiles(container);
    } catch (error) {
      toast(error.message || "提交失败", "error");
      button.disabled = false;
    }
    return;
  }

  if (action === "delete") {
    const confirmed = await confirmDialog({
      title: "删除文件",
      message: "删除后文件将对所有人不可见（软删除），文件编号不可复用。确定删除吗？",
      okText: "删除",
      danger: true,
    });
    if (!confirmed) return;
    button.disabled = true;
    const isLastRowOnPage = button.closest("tbody")?.querySelectorAll("tr").length === 1;
    try {
      const data = await api.deleteFile(fileId);
      toast((data && data.message) || "文件已删除", "success");
      if (isLastRowOnPage && state.page > 1) state.page -= 1;
      await loadFiles(container);
    } catch (error) {
      toast(error.message || "删除失败", "error");
      button.disabled = false;
    }
  }
}

/* ---------------- 上传弹窗 ---------------- */
function openUploadModal(container) {
  let submitting = false;

  const modal = openModal({
    title: "上传工艺文件",
    size: "md",
    content: `
      <form id="upload-form" class="form-grid" autocomplete="off">
        <label class="field">
          <span class="field-label">文件名称<span class="required">*</span></span>
          <input class="input" name="file_name" maxlength="255" placeholder="如 主轴加工工艺">
        </label>
        <label class="field">
          <span class="field-label">工序<span class="required">*</span></span>
          <input class="input" name="process_step" maxlength="100" placeholder="如 车削">
        </label>
        <label class="field">
          <span class="field-label">工序代码</span>
          <input class="input" name="process_code" maxlength="4" placeholder="选填，2-4 位大写字母/数字">
        </label>
        <label class="field">
          <span class="field-label">版本号</span>
          <input class="input" name="version" value="V1.0.0" maxlength="20" placeholder="V1.0.0">
        </label>
        <label class="field span-2">
          <span class="field-label">备注</span>
          <textarea class="textarea" name="remarks" maxlength="1000" placeholder="选填，最多 1000 字"></textarea>
        </label>
        <div class="field span-2">
          <span class="field-label">文件<span class="required">*</span></span>
          <div class="file-drop" id="upload-drop">
            <svg class="icon icon-lg"><use href="#icon-upload"/></svg>
            <div class="file-drop-title">点击选择文件，或将文件拖拽到此处</div>
            <div class="file-drop-sub">支持 PDF / Word / Excel / TXT，单个文件最大 50MB</div>
            <input type="file" id="upload-file">
          </div>
          <div id="upload-selected"></div>
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
      <button type="button" class="btn btn-primary" data-action="submit">开始上传</button>`,
  });

  const form = modal.body.querySelector("#upload-form");
  const submitButton = modal.footer.querySelector('[data-action="submit"]');
  const cancelButton = modal.footer.querySelector('[data-action="cancel"]');
  const progress = setupProgress(modal.body);
  const dropZone = setupDropZone(modal.body, {
    dropId: "upload-drop",
    inputId: "upload-file",
    selectedId: "upload-selected",
  });

  cancelButton.addEventListener("click", () => {
    if (!submitting) modal.close();
  });

  submitButton.addEventListener("click", async () => {
    if (submitting) return;

    const file = dropZone.getFile();
    const values = {};
    ["file_name", "process_step", "process_code", "version", "remarks"].forEach((key) => {
      values[key] = String(form.elements[key].value || "").trim();
    });

    if (!file) {
      toast("请选择要上传的文件", "error");
      return;
    }
    if (!values.file_name) {
      toast("请输入文件名称", "error");
      form.elements.file_name.focus();
      return;
    }
    if (!values.process_step) {
      toast("请输入工序", "error");
      form.elements.process_step.focus();
      return;
    }
    if (values.process_code && !/^[A-Z0-9]{2,4}$/.test(values.process_code)) {
      toast("工序代码需为 2-4 位大写字母或数字", "error");
      form.elements.process_code.focus();
      return;
    }
    if (values.version && !/^V\d+\.\d+\.\d+$/.test(values.version)) {
      toast("版本号格式应为 Vx.y.z，如 V1.0.0", "error");
      form.elements.version.focus();
      return;
    }
    const fileError = validateFile(file);
    if (fileError) {
      toast(fileError, "error");
      return;
    }

    submitting = true;
    const restore = withButtonLoading(submitButton, "上传中…");
    cancelButton.disabled = true;
    progress.show();

    try {
      const data = await api.uploadFile({ file, ...values }, (percent) => progress.update(percent));
      const suffix = data && data.file_number ? "：" + data.file_number : "";
      toast("上传成功" + suffix, "success");
      modal.close();
      state.page = 1;
      await loadFiles(container);
    } catch (error) {
      toast(error.message || "上传失败", "error");
      progress.hide();
      restore();
      cancelButton.disabled = false;
      submitting = false;
    }
  });
}
