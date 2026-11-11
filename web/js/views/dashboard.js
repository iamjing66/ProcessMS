/**
 * 概览统计：指标卡片、最近更新文件、状态分布、最近操作
 * 数据来源：GET /api/stats/overview（契约 §7.1）
 */
import { api } from "../api.js";
import { can } from "../auth.js";
import { escapeHtml, formatDateTime, operationLabel, statusBadge } from "../format.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";

const STATUS_META = [
  { key: "draft", label: "草稿", color: "#86909c" },
  { key: "review", label: "待审核", color: "#1677ff" },
  { key: "approval", label: "待批准", color: "#ff7d00" },
  { key: "approved", label: "已批准", color: "#00b42a" },
  { key: "archived", label: "已归档", color: "#722ed1" },
];

function readNumber(source, paths) {
  for (const pathStr of paths) {
    let current = source;
    for (const part of pathStr.split(".")) {
      if (current && typeof current === "object") current = current[part];
      else {
        current = undefined;
        break;
      }
    }
    if (typeof current === "number" && isFinite(current)) return current;
    if (typeof current === "string" && current.trim() !== "" && isFinite(Number(current))) return Number(current);
  }
  return null;
}

/** 归一化统计响应（兼容契约字段与常见别名） */
function normalizeStats(raw) {
  const stats = raw && typeof raw === "object" ? raw : {};
  const byStatus = stats.files && stats.files.by_status ? stats.files.by_status : {};
  const value = {
    total: readNumber(stats, ["files.total", "total_files", "file_total"]),
    draft: readNumber(byStatus, ["draft"]),
    review: readNumber(byStatus, ["pending_review"]),
    approval: readNumber(byStatus, ["pending_approval"]),
    approved: readNumber(byStatus, ["approved"]),
    archived: readNumber(byStatus, ["archived"]),
    myReview: readNumber(stats, ["pending.my_review"]),
    myApproval: readNumber(stats, ["pending.my_approval"]),
    users: readNumber(stats, ["users.total", "total_users"]),
    catalogTime: (stats.catalog && stats.catalog.last_refresh_at) || null,
    catalogCount: readNumber(stats, ["catalog.item_count"]),
    recentOperations: Array.isArray(stats.recent_operations) ? stats.recent_operations : [],
  };
  if (value.total === null) {
    const parts = [value.draft, value.review, value.approval, value.approved, value.archived].filter(
      (n) => typeof n === "number"
    );
    if (parts.length) value.total = parts.reduce((a, b) => a + b, 0);
  }
  return value;
}

function statCard(icon, colorClass, value, label, path) {
  return `
    <div class="stat-card" data-go="${path || ""}" style="${path ? "cursor:pointer" : ""}">
      <div class="stat-icon ${colorClass}"><svg class="icon"><use href="#${icon}"/></svg></div>
      <div>
        <div class="stat-value">${value === null || value === undefined ? "—" : value}</div>
        <div class="stat-label">${label}</div>
      </div>
    </div>`;
}

export async function render(container, context = {}) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>概览统计</h2>
        <p class="page-desc">工艺文件与审批流程的整体运行情况</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn" id="btn-refresh-dashboard">
          <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新</span>
        </button>
      </div>
    </div>
    <div class="stat-grid" id="stat-grid"></div>
    <div class="dashboard-grid">
      <div class="card">
        <div class="card-header">
          <div class="card-title">最近更新的文件</div>
          <button type="button" class="btn btn-sm" data-go="/files">查看全部</button>
        </div>
        <div class="card-body no-pad" id="recent-files"></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">文件状态分布</div></div>
        <div class="card-body" id="status-dist"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title">最近操作</div>
        ${can("user_manage") ? '<button type="button" class="btn btn-sm" data-go="/logs">查看全部</button>' : ""}
      </div>
      <div class="card-body no-pad" id="recent-logs"></div>
    </div>`;

  container.querySelector("#btn-refresh-dashboard").addEventListener("click", () => load(container, true));
  container.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.go));
  });
  // 统计卡片下发给 load 后绑定点击跳转
  bindStatCards(container);

  await load(container, false);
  bindStatCards(container);
}

function bindStatCards(container) {
  container.querySelectorAll(".stat-card[data-go]").forEach((card) => {
    if (!card.dataset.go) return;
    card.onclick = () => navigate(card.dataset.go);
  });
}

async function load(container, manual) {
  const statGrid = container.querySelector("#stat-grid");
  const recentFiles = container.querySelector("#recent-files");
  const statusDist = container.querySelector("#status-dist");
  const recentLogs = container.querySelector("#recent-logs");
  if (!statGrid) return;

  statGrid.innerHTML = Array.from({ length: 4 })
    .map(
      () =>
        '<div class="stat-card"><div class="stat-icon blue"></div><div><div class="stat-value">…</div><div class="stat-label">加载中</div></div></div>'
    )
    .join("");

  let stats;
  try {
    stats = normalizeStats(await api.getStats());
  } catch (error) {
    if (manual) toast("统计接口不可用，已使用文件列表汇总", "warning");
    stats = await fallbackStats();
  }

  statGrid.innerHTML = [
    statCard("icon-file", "blue", stats.total, "工艺文件总数", "/files"),
    statCard("icon-approval", "orange", stats.review, "待审核文件", "/approvals"),
    statCard("icon-check", "purple", stats.approval, "待批准文件", "/approvals"),
    statCard("icon-archive", "green", stats.archived, "已归档文件", "/checklist"),
  ].join("");
  bindStatCards(container);

  // ---- 状态分布 ----
  const distCounts = [stats.draft, stats.review, stats.approval, stats.approved, stats.archived];
  if (distCounts.some((n) => typeof n === "number")) {
    const maxValue = Math.max(1, ...distCounts.map((n) => Number(n) || 0));
    statusDist.innerHTML = `<div class="dist-list">${STATUS_META.map((meta, index) => {
      const count = Number(distCounts[index]) || 0;
      const width = Math.round((count / maxValue) * 100);
      return `
        <div class="dist-row">
          <div class="dist-head">
            <span class="dist-name"><span class="dist-dot" style="background:${meta.color}"></span>${meta.label}</span>
            <span class="dist-count">${count}</span>
          </div>
          <div class="dist-track"><div class="dist-bar" style="width:${width}%;background:${meta.color}"></div></div>
        </div>`;
    }).join("")}</div>`;
  } else {
    statusDist.innerHTML = '<div class="timeline-empty">暂无统计数据</div>';
  }

  // ---- 最近更新文件 ----
  try {
    const result = await api.listFiles({ page: 1, size: 5, sort: "last_update_time", order: "desc" });
    if (!result.items.length) {
      recentFiles.innerHTML = '<div class="timeline-empty" style="padding:20px">暂无文件</div>';
    } else {
      recentFiles.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>编号</th><th>文件名称</th><th>版本</th><th>编制人</th><th>状态</th><th>更新时间</th></tr></thead>
            <tbody>
              ${result.items.map((file) => `
                <tr data-go="/files/${escapeHtml(file._id)}" style="cursor:pointer">
                  <td class="mono">${escapeHtml(file._number || "—")}</td>
                  <td class="cell-name cell-ellipsis">${escapeHtml(file._name || "—")}</td>
                  <td>${escapeHtml(file._version || "—")}</td>
                  <td>${escapeHtml(file._creator || "—")}</td>
                  <td>${statusBadge(file.file_status, file.file_status_text)}</td>
                  <td class="col-num">${formatDateTime(file._updatedAt)}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
      recentFiles.querySelectorAll("tr[data-go]").forEach((row) => {
        row.addEventListener("click", () => navigate(row.dataset.go));
      });
    }
  } catch (error) {
    recentFiles.innerHTML = `<div class="timeline-empty" style="padding:20px">${escapeHtml(error.message)}</div>`;
  }

  // ---- 最近操作（来自统计接口，避免普通用户无全量日志权限） ----
  const operations = stats.recentOperations;
  if (!operations.length) {
    recentLogs.innerHTML = '<div class="timeline-empty" style="padding:20px">暂无操作记录</div>';
  } else {
    recentLogs.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>时间</th><th>操作</th><th>操作人</th><th>详情</th></tr></thead>
          <tbody>
            ${operations.map((log) => {
              const operator = log.operator && typeof log.operator === "object" ? log.operator.real_name || log.operator.username : "";
              const typeText = log.operation_type_text || operationLabel(log.operation_type);
              return `
                <tr>
                  <td class="col-num">${formatDateTime(log.operation_time)}</td>
                  <td>${escapeHtml(typeText || "—")}</td>
                  <td>${escapeHtml(operator || log.operator_name || "—")}</td>
                  <td class="log-detail" title="${escapeHtml(log.operation_details || "")}">${escapeHtml(log.operation_details || "—")}</td>
                </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>`;
  }
}

/** 统计接口不可用时的兜底：按状态查询文件数 */
async function fallbackStats() {
  const statuses = [1, 2, 3, 4, 5];
  const results = await Promise.allSettled(
    statuses.map((status) => api.listFiles({ page: 1, size: 1, status }))
  );
  const counts = results.map((item) => (item.status === "fulfilled" ? item.value.total : null));
  let users = null;
  try {
    const userPage = await api.listUsers({ page: 1, size: 1 });
    users = userPage.total;
  } catch (_) {
    users = null;
  }
  return normalizeStats({
    files: {
      by_status: {
        draft: counts[0],
        pending_review: counts[1],
        pending_approval: counts[2],
        approved: counts[3],
        archived: counts[4],
      },
      total: counts.filter((n) => typeof n === "number").reduce((a, b) => a + b, 0),
    },
    users: { total: users },
    recent_operations: [],
  });
}
