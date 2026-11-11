/**
 * 操作日志（user_manage）：分页、按类型/操作人/时间筛选
 * 契约：GET /api/logs?page&size&operation_type&operator_id&target_type&date_start&date_end
 */
import { api } from "../api.js";
import { escapeHtml, formatDateTime, operationLabel } from "../format.js";
import {
  bindPagination,
  paginationHtml,
  showEmpty,
  showError,
  showLoading,
} from "../ui.js";

const OPERATION_TYPES = [
  { value: "", label: "全部类型" },
  { value: "upload", label: "上传" },
  { value: "update", label: "更新" },
  { value: "submit_review", label: "提交审核" },
  { value: "review_pass", label: "审核通过" },
  { value: "review_reject", label: "审核驳回" },
  { value: "approve_pass", label: "批准通过" },
  { value: "approve_reject", label: "批准驳回" },
  { value: "archive", label: "归档" },
  { value: "delete", label: "删除" },
  { value: "download", label: "下载" },
  { value: "login", label: "登录" },
  { value: "register", label: "注册" },
  { value: "change_password", label: "修改密码" },
  { value: "catalog_refresh", label: "刷新清单" },
  { value: "user_create", label: "创建用户" },
  { value: "user_update", label: "更新用户" },
  { value: "user_disable", label: "禁用用户" },
  { value: "role_update", label: "角色变更" },
];

const TARGET_TYPES = [
  { value: "", label: "全部对象" },
  { value: "file", label: "文件" },
  { value: "user", label: "用户" },
  { value: "auth", label: "认证" },
  { value: "catalog", label: "清单" },
];

const state = {
  page: 1,
  size: 20,
  filters: { operation_type: "", operator_id: "", target_type: "", date_start: "", date_end: "" },
};

export async function render(container) {
  const typeOptions = OPERATION_TYPES.map(
    (item) => `<option value="${item.value}" ${state.filters.operation_type === item.value ? "selected" : ""}>${item.label}</option>`
  ).join("");
  const targetOptions = TARGET_TYPES.map(
    (item) => `<option value="${item.value}" ${state.filters.target_type === item.value ? "selected" : ""}>${item.label}</option>`
  ).join("");

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>操作日志</h2>
        <p class="page-desc">审计文件上传、审批、归档、用户管理等全部关键操作</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn" id="btn-refresh-logs">
          <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新</span>
        </button>
      </div>
    </div>

    <div class="card">
      <form class="filter-form" id="log-filter" autocomplete="off">
        <div class="filter-field">
          <span class="field-label">操作类型</span>
          <select class="select" name="operation_type">${typeOptions}</select>
        </div>
        <div class="filter-field">
          <span class="field-label">操作人 ID</span>
          <input class="input" name="operator_id" type="number" min="1" placeholder="用户 ID" value="${escapeHtml(state.filters.operator_id)}">
        </div>
        <div class="filter-field">
          <span class="field-label">对象类型</span>
          <select class="select" name="target_type">${targetOptions}</select>
        </div>
        <div class="filter-field wide">
          <span class="field-label">操作日期</span>
          <div class="date-range">
            <input type="date" class="input" name="date_start" value="${escapeHtml(state.filters.date_start)}">
            <span class="sep">至</span>
            <input type="date" class="input" name="date_end" value="${escapeHtml(state.filters.date_end)}">
          </div>
        </div>
        <div class="filter-actions">
          <button type="submit" class="btn btn-primary">
            <svg class="icon"><use href="#icon-search"/></svg><span>查询</span>
          </button>
          <button type="button" class="btn" id="btn-reset-log-filter">重置</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">日志记录 <span class="count" id="log-count"></span></div>
      </div>
      <div id="log-table-area"></div>
    </div>`;

  const form = container.querySelector("#log-filter");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    Object.keys(state.filters).forEach((key) => {
      state.filters[key] = String(formData.get(key) || "").trim();
    });
    state.page = 1;
    loadLogs(container);
  });

  container.querySelector("#btn-reset-log-filter").addEventListener("click", () => {
    Object.keys(state.filters).forEach((key) => {
      state.filters[key] = "";
    });
    form.reset();
    state.page = 1;
    loadLogs(container);
  });

  container.querySelector("#btn-refresh-logs").addEventListener("click", () => loadLogs(container));

  await loadLogs(container);
}

async function loadLogs(container) {
  const area = container.querySelector("#log-table-area");
  if (!area) return;
  showLoading(area);

  const params = { page: state.page, size: state.size };
  Object.entries(state.filters).forEach(([key, value]) => {
    if (value) params[key] = value;
  });

  try {
    const result = await api.listLogs(params);
    state.page = result.page || 1;
    state.size = result.size || state.size;
    const countEl = container.querySelector("#log-count");
    if (countEl) countEl.textContent = `共 ${result.total} 条`;
    renderTable(area, result, container);
  } catch (error) {
    const retry = showError(area, error.message || "操作日志加载失败");
    retry.addEventListener("click", () => loadLogs(container));
  }
}

function renderTable(area, result, container) {
  if (!result.items.length) {
    showEmpty(area, "暂无操作日志", "调整筛选条件后重试");
    return;
  }

  area.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>操作时间</th>
            <th>操作类型</th>
            <th>操作人</th>
            <th>对象</th>
            <th>操作详情</th>
            <th>IP 地址</th>
          </tr>
        </thead>
        <tbody>
          ${result.items
            .map((log) => {
              const targetType = log.target_type || "";
              const targetLabel =
                targetType === "file"
                  ? "文件"
                  : targetType === "user"
                    ? "用户"
                    : targetType === "auth"
                      ? "认证"
                      : targetType === "catalog"
                        ? "清单"
                        : "—";
              const targetId = log.target_id ?? log.file_id ?? "";
              return `
                <tr>
                  <td class="col-num">${formatDateTime(log._time)}</td>
                  <td>${escapeHtml(log._typeText || operationLabel(log.operation_type))}</td>
                  <td>${escapeHtml(log._operator || "—")}</td>
                  <td>${targetId !== "" ? `${targetLabel} #${escapeHtml(targetId)}` : escapeHtml(targetLabel)}</td>
                  <td class="log-detail" title="${escapeHtml(log._details || "")}">${escapeHtml(log._details || "—")}</td>
                  <td class="mono">${escapeHtml(log.ip_address || "—")}</td>
                </tr>`;
            })
            .join("")}
        </tbody>
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
    loadLogs(container);
  });
}
