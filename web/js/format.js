/**
 * 格式化与展示辅助函数：转义、日期、文件大小、状态徽标、角色名
 */
import { ROLE_LABELS } from "./config.js";

/** HTML 转义，所有来自接口的文本在拼接 HTML 前必须转义 */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** 空值占位 */
export function dash(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return escapeHtml(value);
}

/** 解析后端时间：支持 ISO 字符串、时间戳（秒/毫秒）、空值 */
function toDate(value) {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") {
    const ms = value < 1e12 ? value * 1000 : value;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? null : d;
  }
  const text = String(value).trim();
  // 后端可能返回 "2025-01-01 12:00:00"（无时区），按本地时间解析
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(text) ? text.replace(" ", "T") : text;
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** 日期时间：YYYY-MM-DD HH:mm */
export function formatDateTime(value) {
  const d = toDate(value);
  if (!d) return "—";
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** 仅日期：YYYY-MM-DD */
export function formatDate(value) {
  const d = toDate(value);
  if (!d) return "—";
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** 文件大小：KB / MB */
export function formatFileSize(bytes) {
  if (bytes === null || bytes === undefined || bytes === "") return "—";
  const n = Number(bytes);
  if (!isFinite(n) || n < 0) return "—";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(2) + " MB";
  return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

/** 日期时间输入框的当前值：YYYY-MM-DD */
export function todayString() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/* ------------------------------------------------------------------
 * 文件状态映射
 * 文档定义（int）：0 已删除 / 1 草稿 / 2 待审核 / 3 待批准 / 4 已批准 / 5 已归档
 * 同时兼容历史字符串枚举，避免后端调整时前端白屏
 * ------------------------------------------------------------------ */
const INT_STATUS = {
  0: { key: "deleted", text: "已删除", cls: "badge-deleted" },
  1: { key: "draft", text: "草稿", cls: "badge-draft" },
  2: { key: "review", text: "待审核", cls: "badge-review" },
  3: { key: "approval", text: "待批准", cls: "badge-approval" },
  4: { key: "approved", text: "已批准", cls: "badge-approved" },
  5: { key: "archived", text: "已归档", cls: "badge-archived" },
};

const STR_STATUS = {
  draft: { key: "draft", text: "草稿", cls: "badge-draft" },
  pending_review: { key: "review", text: "待审核", cls: "badge-review" },
  reviewed: { key: "review", text: "待审核", cls: "badge-review" },
  pending_approval: { key: "approval", text: "待批准", cls: "badge-approval" },
  approved: { key: "approved", text: "已批准", cls: "badge-approved" },
  archived: { key: "archived", text: "已归档", cls: "badge-archived" },
  deleted: { key: "deleted", text: "已删除", cls: "badge-deleted" },
};

/** 把状态值统一成 { key, text, cls } */
export function normalizeFileStatus(value, label) {
  if (value === null || value === undefined || value === "") {
    return { key: "unknown", text: label || "未知", cls: "badge-default" };
  }
  if (typeof value === "number" || /^\d+$/.test(String(value))) {
    const found = INT_STATUS[Number(value)];
    if (found) return found;
  }
  const key = String(value).toLowerCase();
  const found = STR_STATUS[key];
  if (found) return found;
  return { key: "unknown", text: label || String(value), cls: "badge-default" };
}

/** 状态徽标 HTML */
export function statusBadge(value, label) {
  const st = normalizeFileStatus(value, label);
  return `<span class="badge ${st.cls}">${escapeHtml(st.text)}</span>`;
}

/** 审批步骤状态（0 待处理 / 1 通过 / 2 驳回），兼容字符串 */
export function normalizeStepStatus(value, label) {
  if (value === null || value === undefined || value === "") {
    return { key: "pending", text: label || "待处理", cls: "badge-gray" };
  }
  if (typeof value === "number" || /^\d+$/.test(String(value))) {
    const n = Number(value);
    if (n === 1) return { key: "done", text: "已通过", cls: "badge-approved" };
    if (n === 2) return { key: "rejected", text: "已驳回", cls: "badge-deleted" };
    return { key: "pending", text: "待处理", cls: "badge-gray" };
  }
  const key = String(value).toLowerCase();
  if (["approved", "pass", "passed", "done", "agree"].includes(key)) {
    return { key: "done", text: "已通过", cls: "badge-approved" };
  }
  if (["rejected", "reject", "denied"].includes(key)) {
    return { key: "rejected", text: "已驳回", cls: "badge-deleted" };
  }
  return { key: "pending", text: label || "待处理", cls: "badge-gray" };
}

/** 角色数组统一为 code 字符串数组（兼容字符串、对象、role 字段） */
export function normalizeRoleCodes(roles) {
  if (!roles) return [];
  if (typeof roles === "string") return [roles];
  if (!Array.isArray(roles)) return [];
  const codes = [];
  for (const role of roles) {
    if (!role) continue;
    if (typeof role === "string") codes.push(role);
    else if (typeof role === "object") {
      const code = role.name || role.code || role.role_name || role.role;
      if (code) codes.push(String(code));
    }
  }
  return Array.from(new Set(codes));
}

/** 角色 code 转中文名 */
export function roleLabel(code) {
  return ROLE_LABELS[code] || code;
}

/** 角色数组转中文展示文本 */
export function roleText(roles) {
  const codes = normalizeRoleCodes(roles);
  if (!codes.length) return "—";
  return codes.map(roleLabel).join(" / ");
}

/** 操作类型中文映射（日志/详情展示） */
export const OPERATION_LABELS = {
  upload: "上传",
  update: "更新",
  submit_review: "提交审核",
  review: "审核",
  review_pass: "审核通过",
  review_reject: "审核驳回",
  approve: "批准",
  approve_pass: "批准通过",
  approve_reject: "批准驳回",
  archive: "归档",
  delete: "删除",
  download: "下载",
  login: "登录",
  register: "注册",
  change_password: "修改密码",
  catalog_refresh: "刷新清单",
  user_create: "创建用户",
  user_update: "更新用户",
  user_disable: "禁用用户",
  role_update: "角色变更",
};

export function operationLabel(type) {
  if (!type) return "—";
  return OPERATION_LABELS[type] || String(type);
}

/** 截断长文本 */
export function truncate(text, max = 60) {
  if (text === null || text === undefined) return "";
  const s = String(text);
  return s.length > max ? s.slice(0, max) + "…" : s;
}
