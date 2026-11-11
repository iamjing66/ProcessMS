/**
 * 通用 UI 组件：轻提示、弹窗、确认框、空/加载/错误状态、分页
 */
import { escapeHtml } from "./format.js";
import { PAGE_SIZE_OPTIONS } from "./config.js";

/* ---------------- 轻提示 toast ---------------- */
const TOAST_ICONS = {
  success: "icon-check",
  error: "icon-warning",
  warning: "icon-warning",
  info: "icon-warning",
};

export function toast(message, type = "info", duration = 3000) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const el = document.createElement("div");
  el.className = "toast toast-" + (TOAST_ICONS[type] ? type : "info");
  el.innerHTML = `<svg class="icon"><use href="#${TOAST_ICONS[type] || "icon-warning"}"/></svg><span></span>`;
  el.querySelector("span").textContent = message || "";
  root.appendChild(el);
  const remove = () => {
    el.classList.add("is-hiding");
    setTimeout(() => el.remove(), 200);
  };
  const timer = setTimeout(remove, duration);
  el.addEventListener("click", () => {
    clearTimeout(timer);
    remove();
  });
}

/* ---------------- 弹窗 ---------------- */
let modalSeq = 0;

/**
 * 打开弹窗
 * @returns {{close:Function, body:HTMLElement, footer:HTMLElement, overlay:HTMLElement}}
 */
export function openModal(options = {}) {
  const {
    title = "",
    content = "",
    footer = null,
    size = "md",
    closable = true,
    onClose = null,
  } = options;

  const root = document.getElementById("modal-root");
  if (!root) throw new Error("弹窗容器不存在");

  const id = "modal-" + ++modalSeq;
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = id;
  const sizeClass = size === "sm" ? "modal-sm" : size === "lg" ? "modal-lg" : "";
  overlay.innerHTML = `
    <div class="modal ${sizeClass}" role="dialog" aria-modal="true" aria-labelledby="${id}-title">
      <div class="modal-header">
        <h3 class="modal-title" id="${id}-title"></h3>
        <button type="button" class="modal-close" aria-label="关闭">
          <svg class="icon"><use href="#icon-close"/></svg>
        </button>
      </div>
      <div class="modal-body"></div>
      <div class="modal-footer" hidden></div>
    </div>`;

  overlay.querySelector(".modal-title").textContent = title;
  const body = overlay.querySelector(".modal-body");
  if (typeof content === "string") body.innerHTML = content;
  else if (content instanceof Node) body.appendChild(content);

  const footerEl = overlay.querySelector(".modal-footer");
  if (footer) {
    footerEl.hidden = false;
    if (typeof footer === "string") footerEl.innerHTML = footer;
    else if (footer instanceof Node) footerEl.appendChild(footer);
  }

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    overlay.remove();
    document.removeEventListener("keydown", onKeydown);
    if (typeof onClose === "function") onClose();
  }
  function onKeydown(e) {
    if (e.key === "Escape" && closable) close();
  }

  const closeBtn = overlay.querySelector(".modal-close");
  if (!closable) closeBtn.remove();
  else closeBtn.addEventListener("click", close);

  overlay.addEventListener("mousedown", (e) => {
    if (closable && e.target === overlay) close();
  });
  document.addEventListener("keydown", onKeydown);
  root.appendChild(overlay);

  // 聚焦第一个可交互元素，提升键盘可用性
  const first = overlay.querySelector("input:not([type=hidden]), select, textarea, button.btn-primary");
  if (first) setTimeout(() => first.focus(), 30);

  return { close, body, footer: footerEl, overlay };
}

/** 确认对话框，返回 Promise<boolean> */
export function confirmDialog(options = {}) {
  const {
    title = "操作确认",
    message = "",
    okText = "确定",
    cancelText = "取消",
    danger = false,
  } = options;

  return new Promise((resolve) => {
    let decided = false;
    const modal = openModal({
      title,
      size: "sm",
      content: `<div class="confirm-content">${escapeHtml(message)}</div>`,
      footer: `
        <button type="button" class="btn" data-action="cancel">${escapeHtml(cancelText)}</button>
        <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"}" data-action="ok">${escapeHtml(okText)}</button>`,
      onClose: () => {
        if (!decided) resolve(false);
      },
    });

    const finish = (value) => {
      decided = true;
      modal.close();
      resolve(value);
    };
    modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => finish(false));
    modal.footer.querySelector('[data-action="ok"]').addEventListener("click", () => finish(true));
  });
}

/* ---------------- 占位状态 ---------------- */
export function showLoading(container, text = "加载中…") {
  container.innerHTML = `<div class="loading-state"><span class="spinner"></span><span>${escapeHtml(text)}</span></div>`;
}

export function showEmpty(container, title = "暂无数据", desc = "") {
  container.innerHTML = `
    <div class="empty-state">
      <svg class="icon"><use href="#icon-inbox"/></svg>
      <div class="empty-state-title">${escapeHtml(title)}</div>
      ${desc ? `<div class="empty-state-desc">${escapeHtml(desc)}</div>` : ""}
    </div>`;
}

export function showError(container, message = "加载失败") {
  container.innerHTML = `
    <div class="error-state">
      <svg class="icon"><use href="#icon-warning"/></svg>
      <div class="error-state-msg">${escapeHtml(message)}</div>
      <button type="button" class="btn btn-sm" data-action="retry">重试</button>
    </div>`;
  const retry = container.querySelector('[data-action="retry"]');
  return retry;
}

/* ---------------- 分页 ---------------- */
/** 生成分页 HTML（页码 + 每页条数），view 负责绑定事件 */
export function paginationHtml({ page = 1, size = 10, total = 0, pages = 1 } = {}) {
  const totalPages = Math.max(1, Number(pages) || 1);
  const current = Math.min(Math.max(1, Number(page) || 1), totalPages);
  const pageButtons = [];

  const pushPage = (n) => {
    pageButtons.push(
      `<button type="button" class="page-btn ${n === current ? "active" : ""}" data-page="${n}">${n}</button>`
    );
  };
  const pushEllipsis = () => pageButtons.push('<span class="page-ellipsis">…</span>');

  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pushPage(i);
  } else if (current <= 4) {
    for (let i = 1; i <= 5; i++) pushPage(i);
    pushEllipsis();
    pushPage(totalPages);
  } else if (current >= totalPages - 3) {
    pushPage(1);
    pushEllipsis();
    for (let i = totalPages - 4; i <= totalPages; i++) pushPage(i);
  } else {
    pushPage(1);
    pushEllipsis();
    for (let i = current - 1; i <= current + 1; i++) pushPage(i);
    pushEllipsis();
    pushPage(totalPages);
  }

  const sizeOptions = PAGE_SIZE_OPTIONS.map(
    (n) => `<option value="${n}" ${n === Number(size) ? "selected" : ""}>${n} 条/页</option>`
  ).join("");

  const start = total === 0 ? 0 : (current - 1) * Number(size) + 1;
  const end = Math.min(current * Number(size), Number(total) || 0);

  return `
    <div class="pagination">
      <div class="pagination-info">共 <b>${Number(total) || 0}</b> 条，当前显示 ${start}-${end} 条</div>
      <div class="pagination-controls">
        <button type="button" class="page-btn" data-page="${current - 1}" ${current <= 1 ? "disabled" : ""} title="上一页">
          <svg class="icon"><use href="#icon-chevron-left"/></svg>
        </button>
        ${pageButtons.join("")}
        <button type="button" class="page-btn" data-page="${current + 1}" ${current >= totalPages ? "disabled" : ""} title="下一页">
          <svg class="icon"><use href="#icon-chevron-right"/></svg>
        </button>
        <div class="page-size">
          <select class="select" data-page-size aria-label="每页条数">${sizeOptions}</select>
        </div>
      </div>
    </div>`;
}

/**
 * 绑定分页事件
 * @param {HTMLElement} container 包含分页的容器
 * @param {Function} onChange ({page,size}) => void
 */
export function bindPagination(container, onChange) {
  container.querySelectorAll(".page-btn[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      const page = Number(btn.dataset.page);
      if (!page || page < 1) return;
      onChange({ page });
    });
  });
  const sizeSelect = container.querySelector("[data-page-size]");
  if (sizeSelect) {
    sizeSelect.addEventListener("change", () => onChange({ page: 1, size: Number(sizeSelect.value) }));
  }
}

/* ---------------- 表单辅助 ---------------- */
/** 读取表单内所有 [name] 控件的值（复选框返回数组） */
export function getFormValues(form) {
  const values = {};
  form.querySelectorAll("[name]").forEach((field) => {
    if (field.type === "checkbox") {
      if (field.name.endsWith("[]")) {
        const key = field.name.slice(0, -2);
        values[key] = values[key] || [];
        if (field.checked) values[key].push(field.value);
      } else {
        values[field.name] = field.checked;
      }
    } else if (field.type === "radio") {
      if (field.checked) values[field.name] = field.value;
    } else {
      values[field.name] = field.value;
    }
  });
  return values;
}

/** 设置按钮为加载中状态，返回恢复函数 */
export function withButtonLoading(button, loadingText = "处理中…") {
  const original = button.innerHTML;
  button.disabled = true;
  button.classList.add("is-loading");
  button.textContent = loadingText;
  return () => {
    button.disabled = false;
    button.classList.remove("is-loading");
    button.innerHTML = original;
  };
}

/** 阻止事件冒泡快捷方法（表格行内按钮使用） */
export function stopPropagation(e) {
  e.stopPropagation();
}
