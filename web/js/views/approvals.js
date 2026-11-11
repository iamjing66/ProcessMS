/**
 * 待办审批：按角色权限展示 待审核 / 待批准 / 待归档 列表，支持通过/驳回/归档
 * 契约：GET /api/approvals/pending?type=review|approve；待归档取 file_status=4
 */
import { api } from "../api.js";
import { can, getCurrentUser } from "../auth.js";
import { escapeHtml, formatDateTime, statusBadge } from "../format.js";
import { navigate } from "../router.js";
import {
  bindPagination,
  openModal,
  paginationHtml,
  showEmpty,
  showError,
  showLoading,
  toast,
  withButtonLoading,
} from "../ui.js";

const TABS = [
  { key: "review", label: "待审核", perm: "review" },
  { key: "approve", label: "待批准", perm: "approve" },
  { key: "archive", label: "待归档", perm: "archive" },
];

const state = {
  active: "review",
  size: 10,
  keyword: "",
  pages: { review: 1, approve: 1, archive: 1 },
  counts: { review: null, approve: null, archive: null },
};

function visibleTabs() {
  return TABS.filter((tab) => can(tab.perm));
}

export async function render(container, context = {}) {
  const allowedTabs = visibleTabs();
  if (!allowedTabs.length) {
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h2>待办审批</h2>
          <p class="page-desc">处理分配给当前账号的审核、批准与归档任务</p>
        </div>
      </div>
      <div class="card">
        <div class="empty-state">
          <svg class="icon"><use href="#icon-inbox"/></svg>
          <div class="empty-state-title">当前账号没有待办审批权限</div>
          <div class="empty-state-desc">需要审核（review）、批准（approve）或归档（archive）权限；请联系管理员分配角色。</div>
        </div>
      </div>`;
    return;
  }
  if (!allowedTabs.some((tab) => tab.key === state.active)) {
    state.active = allowedTabs[0].key;
  }

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>待办审批</h2>
        <p class="page-desc">处理分配给当前账号的审核、批准与归档任务</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn" id="btn-refresh-approvals">
          <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新</span>
        </button>
      </div>
    </div>

    <div class="card">
      <div class="tabs" id="approval-tabs"></div>
      <form class="filter-form" id="approval-filter" style="padding:14px 18px 4px" autocomplete="off">
        <div class="filter-field wide">
          <span class="field-label">关键字</span>
          <input class="input" name="keyword" maxlength="100" placeholder="文件名称 / 编号模糊匹配" value="${escapeHtml(state.keyword)}">
        </div>
        <div class="filter-actions">
          <button type="submit" class="btn btn-primary">
            <svg class="icon"><use href="#icon-search"/></svg><span>查询</span>
          </button>
        </div>
      </form>
      <div id="approval-area"></div>
    </div>`;

  container.querySelector("#btn-refresh-approvals").addEventListener("click", () => {
    loadCounts(container);
    loadList(container);
  });
  container.querySelector("#approval-filter").addEventListener("submit", (event) => {
    event.preventDefault();
    state.keyword = String(new FormData(event.target).get("keyword") || "").trim();
    state.pages[state.active] = 1;
    loadList(container);
  });

  renderTabs(container);
  loadCounts(container);
  await loadList(container);
}

function renderTabs(container) {
  const tabsEl = container.querySelector("#approval-tabs");
  const tabs = visibleTabs();
  tabsEl.innerHTML = tabs
    .map((tab) => {
      const count = state.counts[tab.key];
      return `
        <button type="button" class="tab ${state.active === tab.key ? "active" : ""}" data-tab="${tab.key}">
          ${tab.label}${count !== null && count !== undefined ? `<span class="tab-count">${count}</span>` : ""}
        </button>`;
    })
    .join("");
  tabsEl.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.active === button.dataset.tab) return;
      state.active = button.dataset.tab;
      state.pages[state.active] = 1;
      renderTabs(container);
      loadList(container);
    });
  });
}

async function loadCounts(container) {
  const tabs = visibleTabs();
  await Promise.all(
    tabs.map(async (tab) => {
      try {
        if (tab.key === "archive") {
          const result = await api.pendingArchive(1, 1);
          state.counts[tab.key] = result.total;
        } else {
          const result = await api.pendingApprovals(tab.key, 1, 1);
          state.counts[tab.key] = result.total;
        }
      } catch (_) {
        state.counts[tab.key] = null;
      }
    })
  );
  renderTabs(container);
}

async function loadList(container) {
  const area = container.querySelector("#approval-area");
  if (!area) return;
  showLoading(area);
  const page = state.pages[state.active] || 1;

  try {
    let result;
    if (state.active === "archive") {
      result = await api.pendingArchive(page, state.size, state.keyword);
    } else {
      result = await api.pendingApprovals(state.active, page, state.size, state.keyword);
    }
    state.pages[state.active] = result.page || page;
    renderList(area, result, container);
  } catch (error) {
    const retry = showError(area, error.message || "待办列表加载失败");
    retry.addEventListener("click", () => loadList(container));
  }
}

function renderList(area, result, container) {
  if (!result.items.length) {
    const messages = {
      review: ["暂无待审核文件", "工程提交审核后，分配给您的审核任务会显示在这里"],
      approve: ["暂无待批准文件", "组长审核通过后，分配给您的批准任务会显示在这里"],
      archive: ["暂无待归档文件", "主管批准通过的文件会显示在这里，可执行归档"],
    };
    const [title, desc] = messages[state.active] || ["暂无待办", ""];
    showEmpty(area, title, desc);
    return;
  }

  const html = result.items
    .map((item) => {
      const file = item._file || {};
      const status = statusBadge(file.file_status, file.file_status_text);
      const meta = [];
      if (item._stepName) meta.push(`当前环节：${escapeHtml(item._stepName)}`);
      if (state.active !== "archive") {
        meta.push(`提交人：${escapeHtml(item._initiator || "—")}`);
        meta.push(`提交时间：${formatDateTime(item._submittedAt)}`);
      } else {
        meta.push(`批准时间：${formatDateTime(file._approvedAt || file._updatedAt)}`);
      }
      const actions =
        state.active === "archive"
          ? `
            <button type="button" class="btn btn-sm btn-primary" data-action="archive" data-id="${escapeHtml(file._id)}">归档</button>
            <button type="button" class="btn btn-sm" data-action="detail" data-id="${escapeHtml(file._id)}">详情</button>`
          : `
            <button type="button" class="btn btn-sm btn-primary" data-action="pass" data-id="${escapeHtml(file._id)}" data-name="${escapeHtml(file._name || "")}">通过</button>
            <button type="button" class="btn btn-sm btn-danger" data-action="reject" data-id="${escapeHtml(file._id)}" data-name="${escapeHtml(file._name || "")}">驳回</button>
            <button type="button" class="btn btn-sm" data-action="detail" data-id="${escapeHtml(file._id)}">详情</button>`;

      return `
        <div class="approval-item">
          <div class="approval-main">
            <div class="approval-title">
              <span class="cell-name">${escapeHtml(file._name || "—")}</span>
              ${status}
              <span class="mono" style="font-weight:400">${escapeHtml(file._number || "")}</span>
            </div>
            <div class="approval-sub">
              <span>版本 ${escapeHtml(file._version || "—")}</span>
              <span>工序 ${escapeHtml(file._step || "—")}</span>
              <span>编制人 ${escapeHtml(file._creator || "—")}</span>
              ${meta.map((text) => `<span>${text}</span>`).join("")}
            </div>
          </div>
          <div class="approval-actions">${actions}</div>
        </div>`;
    })
    .join("");

  area.innerHTML = `<div class="approval-list">${html}</div>${paginationHtml(result)}`;

  bindPagination(area, ({ page, size }) => {
    if (size) {
      state.size = size;
      state.pages[state.active] = 1;
    } else {
      state.pages[state.active] = page;
    }
    loadList(container);
  });

  area.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const fileId = button.dataset.id;
      const action = button.dataset.action;
      if (action === "detail") {
        navigate("/files/" + fileId);
        return;
      }
      if (action === "archive") {
        openArchiveModal(fileId, container);
        return;
      }
      openDecisionModal(fileId, button.dataset.name || "", action, container);
    });
  });
}

function openDecisionModal(fileId, fileName, action, container) {
  const isReview = state.active === "review";
  const modal = openModal({
    title: isReview ? "审核文件" : "批准文件",
    size: "sm",
    content: `
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-tip">文件：${escapeHtml(fileName || "—")}。${isReview ? "审核通过后进入主管批准环节" : "批准通过后进入待归档"}；驳回则退回草稿，驳回意见必填。</div>
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
        ? await api.review(fileId, result, comment)
        : await api.approve(fileId, result, comment);
      toast((data && data.message) || "操作成功", "success");
      modal.close();
      loadCounts(container);
      await loadList(container);
    } catch (error) {
      toast(error.message || "操作失败", "error");
      buttons.forEach((button) => (button.disabled = false));
    }
  }

  modal.footer.querySelector('[data-action="reject"]').addEventListener("click", () => decide("reject"));
  modal.footer.querySelector('[data-action="pass"]').addEventListener("click", () => decide("pass"));
}

function openArchiveModal(fileId, container) {
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
      const data = await api.archive(fileId, comment);
      toast((data && data.message) || "归档成功，文件清单已更新", "success");
      modal.close();
      loadCounts(container);
      await loadList(container);
    } catch (error) {
      toast(error.message || "归档失败", "error");
      restore();
    }
  });
}
