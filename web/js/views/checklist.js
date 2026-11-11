/**
 * 文件清单：最新快照信息 + 条目表格 + 手动刷新（catalog_manage 权限）
 * 契约：GET /api/catalogs、POST /api/catalogs/refresh
 */
import { api } from "../api.js";
import { can } from "../auth.js";
import { escapeHtml, formatDateTime, formatFileSize, statusBadge } from "../format.js";
import {
  bindPagination,
  confirmDialog,
  paginationHtml,
  showEmpty,
  showError,
  showLoading,
  toast,
  withButtonLoading,
} from "../ui.js";

const state = { page: 1, size: 20, keyword: "" };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>文件清单</h2>
        <p class="page-desc">已批准/已归档文件的清单快照，归档或手动刷新时自动更新</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn" id="btn-refresh-list">
          <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新列表</span>
        </button>
        ${can("catalog_manage") ? '<button type="button" class="btn btn-primary" id="btn-refresh-catalog"><svg class="icon"><use href="#icon-refresh"/></svg><span>手动刷新清单</span></button>' : ""}
      </div>
    </div>

    <div id="catalog-snapshot"></div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">清单条目 <span class="count" id="catalog-count"></span></div>
        <form class="filter-form" id="catalog-filter" style="padding:0" autocomplete="off">
          <div class="filter-field wide" style="width:240px">
            <input class="input" name="keyword" maxlength="100" placeholder="编号 / 名称 / 工序模糊匹配" value="${escapeHtml(state.keyword)}">
          </div>
          <div class="filter-actions" style="margin-left:0">
            <button type="submit" class="btn btn-sm btn-primary">
              <svg class="icon"><use href="#icon-search"/></svg><span>查询</span>
            </button>
          </div>
        </form>
      </div>
      <div id="catalog-table-area"></div>
    </div>`;

  container.querySelector("#btn-refresh-list").addEventListener("click", () => loadCatalog(container));
  container.querySelector("#catalog-filter").addEventListener("submit", (event) => {
    event.preventDefault();
    state.keyword = String(new FormData(event.target).get("keyword") || "").trim();
    state.page = 1;
    loadCatalog(container);
  });

  const manualButton = container.querySelector("#btn-refresh-catalog");
  if (manualButton) {
    manualButton.addEventListener("click", async () => {
      const confirmed = await confirmDialog({
        title: "手动刷新文件清单",
        message: "将基于当前所有已批准/已归档文件全量重建清单快照。确定立即刷新吗？",
        okText: "立即刷新",
      });
      if (!confirmed) return;
      const restore = withButtonLoading(manualButton, "刷新中…");
      try {
        const data = await api.refreshCatalog();
        const snapshot = data && data.snapshot;
        toast((data && data.message) || "文件清单已刷新", "success", 3500);
        if (snapshot && snapshot.item_count !== undefined) {
          toast(`本次快照共 ${snapshot.item_count} 个条目`, "info", 3000);
        }
        state.page = 1;
        await loadCatalog(container);
      } catch (error) {
        toast(error.message || "刷新失败", "error");
      } finally {
        restore();
      }
    });
  }

  await loadCatalog(container);
}

async function loadCatalog(container) {
  const snapshotBox = container.querySelector("#catalog-snapshot");
  const area = container.querySelector("#catalog-table-area");
  if (!area) return;

  showLoading(area);
  try {
    const result = await api.getCatalog({ page: state.page, size: state.size, keyword: state.keyword });
    state.page = result.page || 1;
    state.size = result.size || state.size;
    renderSnapshot(snapshotBox, result);
    renderTable(area, result, container);
  } catch (error) {
    const retry = showError(area, error.message || "文件清单加载失败");
    retry.addEventListener("click", () => loadCatalog(container));
  }
}

function renderSnapshot(box, result) {
  const snapshot = result.snapshot;
  const countEl = document.querySelector("#catalog-count");
  if (countEl) countEl.textContent = `共 ${result.total} 个条目`;

  if (!snapshot) {
    box.innerHTML = `
      <div class="snapshot-bar">
        <div class="snapshot-item">
          <span class="snapshot-label">清单状态</span>
          <span class="snapshot-value">暂无快照</span>
        </div>
        <div class="snapshot-item">
          <span class="snapshot-label">说明</span>
          <span class="snapshot-value" style="font-weight:400;font-size:13px;color:#646a73">归档文件后自动生成，或由资料员/管理员手动刷新</span>
        </div>
      </div>`;
    return;
  }

  box.innerHTML = `
    <div class="snapshot-bar">
      <div class="snapshot-item">
        <span class="snapshot-label">快照编号</span>
        <span class="snapshot-value mono">${escapeHtml(snapshot.no || "—")}</span>
      </div>
      <div class="snapshot-item">
        <span class="snapshot-label">更新方式</span>
        <span class="snapshot-value">${escapeHtml(snapshot.refreshTypeText || "—")}</span>
      </div>
      <div class="snapshot-item">
        <span class="snapshot-label">更新时间</span>
        <span class="snapshot-value">${formatDateTime(snapshot.createdAt)}</span>
      </div>
      <div class="snapshot-item">
        <span class="snapshot-label">条目数</span>
        <span class="snapshot-value">${snapshot.itemCount ?? result.total} 个</span>
      </div>
      ${snapshot.operator ? `<div class="snapshot-item"><span class="snapshot-label">操作人</span><span class="snapshot-value">${escapeHtml(snapshot.operator)}</span></div>` : ""}
      <div class="snapshot-actions">
        <span class="badge badge-approved">最新快照</span>
      </div>
    </div>`;
}

function renderTable(area, result, container) {
  if (!result.items.length) {
    showEmpty(
      area,
      "清单暂无条目",
      state.keyword ? "请调整关键字后重试" : "已批准或已归档的文件会进入清单，归档后可自动刷新"
    );
    return;
  }

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
            <th>批准时间</th>
            <th>大小</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          ${result.items
            .map(
              (item) => `
              <tr>
                <td class="mono">${escapeHtml(item._number || "—")}</td>
                <td class="cell-name cell-ellipsis" title="${escapeHtml(item._name || "")}">${escapeHtml(item._name || "—")}</td>
                <td>${escapeHtml(item._version || "—")}</td>
                <td>${escapeHtml(item._step || "—")}</td>
                <td>${escapeHtml(item._creator || "—")}</td>
                <td>${statusBadge(item.file_status, item.file_status_text)}</td>
                <td class="col-num">${formatDateTime(item._approvedAt || item._updatedAt)}</td>
                <td>${formatFileSize(item._size)}</td>
                <td class="col-actions">
                  <button type="button" class="btn-text" data-download-id="${escapeHtml(item._id)}" data-version="${escapeHtml(item._version || "")}" data-url="${escapeHtml(item._downloadUrl || "")}">下载</button>
                </td>
              </tr>`
            )
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
    loadCatalog(container);
  });

  area.querySelectorAll("button[data-download-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        if (button.dataset.url) {
          await api.downloadByUrl(button.dataset.url, "文件下载");
        } else {
          await api.downloadFile(button.dataset.downloadId, button.dataset.version);
        }
        toast("已开始下载", "success");
      } catch (error) {
        toast(error.message || "下载失败", "error");
      } finally {
        button.disabled = false;
      }
    });
  });
}
