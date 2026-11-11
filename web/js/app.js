/**
 * 应用入口：登录守卫、hash 路由分发、顶栏/侧边栏布局
 */
import { api, setUnauthorizedHandler } from "./api.js";
import { can, canAny, clearAuth, getCurrentUser, getToken, isAdmin, loadMe, logout } from "./auth.js";
import { escapeHtml, roleText } from "./format.js";
import { navigate, resolveRoute } from "./router.js";
import { confirmDialog, showError, toast } from "./ui.js";

import * as loginView from "./views/login.js";
import * as dashboardView from "./views/dashboard.js";
import * as filesView from "./views/files.js";
import * as fileDetailView from "./views/file-detail.js";
import * as approvalsView from "./views/approvals.js";
import * as checklistView from "./views/checklist.js";
import * as usersView from "./views/users.js";
import * as logsView from "./views/logs.js";

/* 路由表：pattern 支持 :param 动态段 */
const definitions = [
  { pattern: "/login", name: "login", title: "登录", view: loginView },
  { pattern: "/dashboard", name: "dashboard", title: "概览统计", view: dashboardView, navPath: "/dashboard" },
  { pattern: "/files", name: "files", title: "文件管理", view: filesView, navPath: "/files" },
  { pattern: "/files/:id", name: "file-detail", title: "文件详情", view: fileDetailView, navPath: "/files" },
  { pattern: "/approvals", name: "approvals", title: "待办审批", view: approvalsView, navPath: "/approvals" },
  { pattern: "/checklist", name: "checklist", title: "文件清单", view: checklistView, navPath: "/checklist" },
  { pattern: "/users", name: "users", title: "用户管理", view: usersView, navPath: "/users", requireAdmin: true },
  { pattern: "/logs", name: "logs", title: "操作日志", view: logsView, navPath: "/logs" },
];

/* 侧边栏导航（visible 决定是否展示） */
const NAV_ITEMS = [
  { path: "/dashboard", label: "概览统计", icon: "icon-dashboard" },
  { path: "/files", label: "文件管理", icon: "icon-file" },
  {
    path: "/approvals",
    label: "待办审批",
    icon: "icon-approval",
    visible: () => canAny(["review", "approve", "archive"]),
  },
  { path: "/checklist", label: "文件清单", icon: "icon-list" },
  { path: "/users", label: "用户管理", icon: "icon-users", visible: () => isAdmin() },
  { path: "/logs", label: "操作日志", icon: "icon-logs", visible: () => can("user_manage") },
];

let routeSeq = 0;

/* ---------------- 布局切换 ---------------- */
function showLogin() {
  const loginScreen = document.getElementById("login-screen");
  const shell = document.getElementById("app-shell");
  if (loginScreen) loginScreen.hidden = false;
  if (shell) shell.hidden = true;
  document.title = "登录 - 工艺文件管理系统";
}

function showApp() {
  const loginScreen = document.getElementById("login-screen");
  const shell = document.getElementById("app-shell");
  if (loginScreen) loginScreen.hidden = true;
  if (shell) shell.hidden = false;
  updateTopbar();
}

function updateTopbar() {
  const user = getCurrentUser() || {};
  const name = user.real_name || user.username || "—";
  const nameEl = document.getElementById("topbar-user-name");
  const avatarEl = document.getElementById("topbar-user-avatar");
  const roleEl = document.getElementById("topbar-user-role");
  if (nameEl) nameEl.textContent = name;
  if (avatarEl) avatarEl.textContent = String(name).slice(0, 1) || "用";
  if (roleEl) roleEl.textContent = roleText(user.roles);
}

function renderNav(activePath) {
  const nav = document.getElementById("nav");
  if (!nav) return;
  const items = NAV_ITEMS.filter((item) => (typeof item.visible === "function" ? item.visible() : true));
  nav.innerHTML = items
    .map(
      (item) => `
      <button type="button" class="nav-item ${item.path === activePath ? "active" : ""}" data-path="${item.path}">
        <svg class="icon"><use href="#${item.icon}"/></svg>
        <span class="nav-text">${escapeHtml(item.label)}</span>
        <span class="nav-badge" data-badge="${item.path}" hidden></span>
      </button>`
    )
    .join("");
  nav.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.path));
  });
  refreshApprovalBadge();
}

/** 侧边栏待办徽标（接口不可用时静默失败，不影响导航） */
async function refreshApprovalBadge() {
  const badge = document.querySelector('[data-badge="/approvals"]');
  if (!badge) return;
  // 仅对具备对应权限的待办发起请求，避免 403 噪声
  const requests = [];
  if (can("review")) requests.push(api.pendingApprovals("review", 1, 1));
  if (can("approve")) requests.push(api.pendingApprovals("approve", 1, 1));
  if (!requests.length) return;
  try {
    const results = await Promise.all(requests.map((promise) => promise.catch(() => ({ total: 0 }))));
    const count = results.reduce((sum, item) => sum + (item.total || 0), 0);
    if (count > 0) {
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.hidden = false;
    }
  } catch (_) {
    /* 无权限或接口暂不可用时不显示徽标 */
  }
}

/* ---------------- 路由 ---------------- */
async function handleRoute() {
  const seq = ++routeSeq;
  const { definition, params, query } = resolveRoute(definitions);

  if (!getToken()) {
    showLogin();
    loginView.render(document.getElementById("login-screen"), { onLoggedIn: handleRoute });
    return;
  }

  if (!definition || definition.name === "login") {
    navigate("/files");
    return;
  }

  if (definition.requireAdmin && !isAdmin()) {
    toast("当前账号无权访问该页面", "warning");
    navigate("/files");
    return;
  }

  if (!getCurrentUser()) {
    try {
      await loadMe();
    } catch (error) {
      if (seq !== routeSeq) return;
      handleUnauthorized();
      return;
    }
    if (seq !== routeSeq) return;
  }

  showApp();
  document.title = definition.title + " - 工艺文件管理系统";
  renderNav(definition.navPath);
  updateTopbar();

  const main = document.getElementById("main-content");
  if (!main) return;
  main.innerHTML = "";
  main.scrollTop = 0;

  try {
    await definition.view.render(main, {
      params,
      query,
      user: getCurrentUser(),
      navigate,
      reload: handleRoute,
    });
  } catch (error) {
    if (seq !== routeSeq) return;
    console.error("[页面渲染失败]", definition.name, error);
    if (error && error.status === 401) return;
    const retry = showError(main, (error && error.message) || "页面加载失败，请稍后重试");
    if (retry) retry.addEventListener("click", handleRoute);
  }
}

/* ---------------- 401 统一处理 ---------------- */
function handleUnauthorized() {
  if (!getToken()) return;
  clearAuth();
  toast("登录状态已失效，请重新登录", "warning");
  if (location.hash === "#/login" || !location.hash) {
    handleRoute();
  } else {
    navigate("/login");
  }
}

/* ---------------- 启动 ---------------- */
function init() {
  setUnauthorizedHandler(handleUnauthorized);

  const logoutButton = document.getElementById("btn-logout");
  if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
      const confirmed = await confirmDialog({
        title: "退出登录",
        message: "确定要退出当前账号吗？退出后需重新登录。",
        okText: "退出登录",
        danger: true,
      });
      if (!confirmed) return;
      logout();
      toast("已退出登录", "success");
      navigate("/login");
    });
  }

  window.addEventListener("hashchange", handleRoute);

  if (!location.hash) {
    location.hash = getToken() ? "#/files" : "#/login";
  }
  handleRoute();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
