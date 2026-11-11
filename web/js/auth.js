/**
 * 登录状态与权限判断
 * token 存 sessionStorage（关闭标签页即失效），用户信息同步缓存
 */
import { TOKEN_KEY, USER_KEY } from "./config.js";
import { normalizeRoleCodes } from "./format.js";
import { api } from "./api.js";

let currentUser = null;

/* 权限别名：后端权限 code 可能使用多种写法，统一收敛 */
const PERMISSION_ALIASES = {
  upload: ["upload", "file:upload", "file_upload"],
  update: ["update", "file:update", "file_update"],
  delete: ["delete", "file:delete", "file_delete"],
  review: ["review", "audit", "file:review", "file_review"],
  approve: ["approve", "approval", "file:approve", "file_approve"],
  reject: ["reject", "file:reject"],
  archive: ["archive", "file:archive", "file_archive"],
  catalog_manage: ["catalog_manage", "catalog:manage", "catalog_manage"],
  user_manage: ["user_manage", "manage_user", "user:manage"],
  view_logs: ["user_manage", "view_logs", "log:view", "audit_log"],
};

/* 角色兜底权限（后端未返回 permissions 时按角色推断） */
const ROLE_PERMISSIONS = {
  admin: ["upload", "update", "delete", "review", "approve", "reject", "archive", "catalog_manage", "user_manage", "view_logs"],
  engineer: ["upload", "update"],
  leader: ["upload", "update", "review", "delete"],
  manager: ["approve"],
  archivist: ["archive", "catalog_manage"],
};

function readJson(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

/** 把后端用户对象归一化 */
export function normalizeUser(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw.user && typeof raw.user === "object") raw = raw.user;
  const roles = normalizeRoleCodes(raw.roles);
  const permissions = normalizePermissions(raw.permissions ?? raw.permission_codes ?? raw.perms);
  return {
    ...raw,
    id: raw.id ?? raw.user_id,
    username: raw.username ?? raw.user_name ?? "",
    real_name: raw.real_name ?? raw.name ?? raw.username ?? "",
    employee_id: raw.employee_id ?? raw.job_number ?? "",
    department: raw.department ?? "",
    position: raw.position ?? "",
    roles,
    permissions,
    is_admin: raw.is_admin === true || roles.includes("admin"),
  };
}

function normalizePermissions(value) {
  if (!value) return [];
  if (typeof value === "string") return [value];
  if (!Array.isArray(value)) return [];
  return Array.from(
    new Set(
      value
        .map((item) => {
          if (!item) return "";
          if (typeof item === "string") return item;
          if (typeof item === "object") return item.code || item.name || item.permission_code || "";
          return "";
        })
        .filter(Boolean)
    )
  );
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function isLoggedIn() {
  return Boolean(getToken());
}

export function getCurrentUser() {
  if (currentUser) return currentUser;
  currentUser = normalizeUser(readJson(USER_KEY));
  return currentUser;
}

export function setCurrentUser(user) {
  currentUser = user;
  if (user) sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  else sessionStorage.removeItem(USER_KEY);
}

/** 登录：保存 token 并拉取当前用户 */
export async function login(username, password) {
  const data = await api.login(username, password);
  if (!data || !data.access_token) throw new Error("登录响应异常：缺少 access_token");
  sessionStorage.setItem(TOKEN_KEY, data.access_token);
  // 登录响应若直接带 user，先缓存，减少一次 /me 失败的影响
  if (data.user) setCurrentUser(normalizeUser(data.user));
  const user = await loadMe();
  return user;
}

/** 拉取 /api/auth/me 并缓存 */
export async function loadMe() {
  const raw = await api.me();
  const user = normalizeUser(raw);
  if (!user) throw new Error("无法获取当前用户信息");
  setCurrentUser(user);
  return user;
}

export function clearAuth() {
  currentUser = null;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

export function logout() {
  clearAuth();
}

/** 后端是否返回了权限信息（未返回时启用兜底策略） */
export function hasPermissionInfo() {
  const user = getCurrentUser();
  return Boolean(user && (user.roles.length || user.permissions.length));
}

export function isAdmin() {
  const user = getCurrentUser();
  return Boolean(user && (user.is_admin || user.roles.includes("admin")));
}

/** 是否具备某项权限 */
export function can(permission) {
  const user = getCurrentUser();
  if (!user) return false;
  if (user.is_admin) return true;
  if (permission === "user_manage") return false;

  const aliases = PERMISSION_ALIASES[permission] || [permission];
  if (user.permissions.length) {
    return user.permissions.some((code) => aliases.includes(code));
  }
  // 无 permissions 时按角色兜底
  if (user.roles.length) {
    return user.roles.some((role) => (ROLE_PERMISSIONS[role] || []).includes(permission));
  }
  // 后端未返回任何权限信息：默认放行（后端仍会做鉴权），避免界面不可用
  return !hasPermissionInfo() ? true : false;
}

export function canAny(permissions) {
  return permissions.some((permission) => can(permission));
}
