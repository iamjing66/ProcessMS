/**
 * 统一 API 访问层（严格对齐 docs/API.md v1.0 冻结契约）
 * - 基础路径 /api，自动附带 Bearer token
 * - 统一错误解析（{"code","message","detail"}）
 * - 401 / 403 AUTH_USER_DISABLED 交由 app.js 统一登出
 * - 接口路径与响应归一化集中在此，视图层只调用语义方法
 */
import { API_BASE, TOKEN_KEY } from "./config.js";
import { normalizeFileStatus, normalizeStepStatus } from "./format.js";

let unauthorizedHandler = null;

/** 注册登录失效处理回调（由 app.js 注入） */
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.code = (data && (data.code || data.error_code)) || "";
  }
}

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

/** 过滤空参数后拼接查询串 */
function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.append(key, String(value));
  });
  const text = search.toString();
  return text ? "?" + text : "";
}

function pick(source, keys) {
  const out = {};
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") out[key] = value;
  }
  return out;
}

/** 从错误响应中提取可展示文案 */
function extractMessage(data, fallback) {
  if (data === null || data === undefined) return fallback;
  if (typeof data === "string") return data;
  if (typeof data.message === "string" && data.message) {
    // 字段级校验错误补充 detail，便于用户定位
    if (data.detail && typeof data.detail === "object" && !Array.isArray(data.detail)) {
      const fields = Object.entries(data.detail)
        .map(([field, reason]) => `${field}: ${reason}`)
        .join("；");
      if (fields) return `${data.message}（${fields}）`;
    }
    return data.message;
  }
  if (typeof data.detail === "string" && data.detail) return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => (item && (item.msg || item.message)) || JSON.stringify(item))
      .join("；");
  }
  if (typeof data === "object") {
    try {
      return JSON.stringify(data);
    } catch (_) {
      return fallback;
    }
  }
  return fallback;
}

/**
 * 核心 fetch 封装
 * @param {string} path 以 / 开头的接口路径（不含 /api）
 */
export async function request(path, options = {}) {
  const { method = "GET", body, headers = {}, responseType = "json", ...rest } = options;
  const finalHeaders = { ...headers };
  let payload = body;
  const isFormData = body instanceof FormData;
  const isUrlEncoded = body instanceof URLSearchParams;

  if (body !== undefined && body !== null && !isFormData && !isUrlEncoded && typeof body !== "string") {
    finalHeaders["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const token = getToken();
  if (token) finalHeaders["Authorization"] = "Bearer " + token;

  let response;
  try {
    response = await fetch(API_BASE + path, {
      method,
      headers: finalHeaders,
      body: payload,
      ...rest,
    });
  } catch (error) {
    if (error && error.name === "AbortError") throw error;
    throw new ApiError("无法连接服务器，请确认后端服务已启动", 0);
  }

  if (response.status === 401) {
    if (typeof unauthorizedHandler === "function") unauthorizedHandler();
    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }
    throw new ApiError(extractMessage(data, "登录状态已失效，请重新登录"), 401, data);
  }

  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }
    // 用户被禁用：清理本地登录态并跳转登录
    if (response.status === 403 && data && data.code === "AUTH_USER_DISABLED") {
      if (typeof unauthorizedHandler === "function") unauthorizedHandler();
    }
    throw new ApiError(extractMessage(data, `请求失败（HTTP ${response.status}）`), response.status, data);
  }

  if (responseType === "blob") return response;
  if (response.status === 204) return null;

  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (_) {
    return text;
  }
}

/** 带进度回调的 XHR 上传（fetch 无法获取上传进度） */
function uploadWithProgress(path, formData, options = {}) {
  const { method = "POST", onProgress } = options;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, API_BASE + path);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && typeof onProgress === "function") {
        onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch (_) {
        data = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (typeof onProgress === "function") onProgress(100);
        resolve(data);
      } else if (xhr.status === 401) {
        if (typeof unauthorizedHandler === "function") unauthorizedHandler();
        reject(new ApiError("登录状态已失效，请重新登录", 401, data));
      } else {
        if (xhr.status === 403 && data && data.code === "AUTH_USER_DISABLED" && typeof unauthorizedHandler === "function") {
          unauthorizedHandler();
        }
        reject(new ApiError(extractMessage(data, `请求失败（HTTP ${xhr.status}）`), xhr.status, data));
      }
    };
    xhr.onerror = () => reject(new ApiError("网络异常，请稍后重试", 0));
    xhr.onabort = () => reject(new ApiError("请求已取消", 0));
    xhr.send(formData);
  });
}

/* ------------------------------------------------------------------
 * 响应归一化（契约已冻结，仍保留防御处理，避免单条脏数据导致白屏）
 * ------------------------------------------------------------------ */
export function normalizePage(data, fallback = {}) {
  const fallbackPage = fallback.page || 1;
  const fallbackSize = fallback.size || 10;

  if (Array.isArray(data)) {
    return { items: data, total: data.length, page: fallbackPage, size: fallbackSize, pages: data.length ? 1 : 0 };
  }
  if (!data || typeof data !== "object") {
    return { items: [], total: 0, page: fallbackPage, size: fallbackSize, pages: 0 };
  }
  const items = Array.isArray(data.items)
    ? data.items
    : Array.isArray(data.list)
      ? data.list
      : Array.isArray(data.records)
        ? data.records
        : [];
  const total = Number(data.total ?? items.length) || 0;
  const page = Number(data.page ?? fallbackPage) || fallbackPage;
  const size = Number(data.size ?? fallbackSize) || fallbackSize;
  const pages = Number(data.pages ?? Math.ceil(total / (size || 10))) || 0;
  return { items, total, page, size, pages };
}

/** 文件对象补充派生字段，视图层直接使用 _xxx */
export function normalizeFile(raw) {
  if (!raw || typeof raw !== "object") return raw;
  const status = normalizeFileStatus(raw.file_status ?? raw.status, raw.file_status_text ?? raw.status_label);
  const creator = raw.creator && typeof raw.creator === "object" ? raw.creator : null;
  const uploader = raw.uploader && typeof raw.uploader === "object" ? raw.uploader : null;
  return {
    ...raw,
    // 注意：CatalogItem 的 id 是条目 id，文件 id 在 file_id；FileItem 只有 id
    _id: raw.file_id ?? raw.id,
    _number: raw.file_number ?? raw.number ?? "",
    _name: raw.file_name ?? raw.name ?? "",
    _version: raw.version ?? "",
    _step: raw.process_step ?? raw.process ?? "",
    _creator: raw.creator_name ?? (creator && (creator.real_name || creator.username)) ?? "",
    _creatorId: raw.creator_id ?? (creator && creator.id),
    _uploader: raw.uploader_name ?? (uploader && (uploader.real_name || uploader.username)) ?? "",
    _uploaderId: raw.uploader_id ?? (uploader && uploader.id),
    _status: status,
    _updatedAt: raw.last_update_time ?? raw.updated_at ?? raw.update_time,
    _createdAt: raw.initial_upload_time ?? raw.created_at ?? raw.upload_time,
    _approvedAt: raw.approved_at,
    _size: raw.file_size ?? raw.size,
    _remarks: raw.remarks ?? raw.remark ?? "",
    _allowed: Array.isArray(raw.allowed_actions) ? raw.allowed_actions : [],
    _downloadUrl: raw.download_url || "",
  };
}

/** 审批步骤归一化 */
function normalizeStep(step) {
  const approver = step.approver && typeof step.approver === "object" ? step.approver : null;
  return {
    number: step.step_number ?? step.step ?? "",
    name: step.step_name ?? step.name ?? "",
    approver: approver ? approver.real_name || approver.username || "" : step.approver_name || "",
    status: normalizeStepStatus(step.approval_status ?? step.status, step.approval_status_text ?? step.status_text),
    time: step.approval_time ?? step.signed_at ?? null,
    comment: step.approval_comment ?? step.comment ?? "",
  };
}

/** 单个 flow 归一化 */
function normalizeFlow(flow) {
  if (!flow || typeof flow !== "object") return null;
  const steps = Array.isArray(flow.steps) ? flow.steps.map(normalizeStep) : [];
  const signatures = Array.isArray(flow.signatures) ? flow.signatures : [];
  const initiator = flow.initiator && typeof flow.initiator === "object" ? flow.initiator : null;
  return {
    id: flow.id ?? flow.flow_id,
    version: flow.version || "",
    flowType: flow.flow_type || "",
    currentStep: flow.current_step,
    status: flow.status,
    statusText: flow.status_text || "",
    initiator: initiator ? initiator.real_name || initiator.username || "" : "",
    createdAt: flow.created_at,
    completedAt: flow.completed_at,
    rejectReason: flow.reject_reason || flow.reject_reason_text || "",
    steps,
    signatures,
  };
}

/** 审批流程接口归一化：返回 { currentFlow, history } */
export function normalizeApproval(data) {
  if (!data || typeof data !== "object") return { currentFlow: null, history: [] };
  const currentFlow = normalizeFlow(data.current_flow || data.flow || null);
  const history = Array.isArray(data.history) ? data.history.map(normalizeFlow).filter(Boolean) : [];
  return { currentFlow, history };
}

/** 清单快照归一化 */
function normalizeSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  const operator = snapshot.operator && typeof snapshot.operator === "object" ? snapshot.operator : null;
  return {
    id: snapshot.id,
    no: snapshot.snapshot_no || "",
    refreshType: snapshot.refresh_type || "",
    refreshTypeText: snapshot.refresh_type_text || (snapshot.refresh_type === "auto" ? "自动" : snapshot.refresh_type === "manual" ? "手动" : ""),
    operator: operator ? operator.real_name || operator.username || "" : "",
    itemCount: snapshot.item_count ?? null,
    createdAt: snapshot.created_at,
  };
}

/** 解析 Content-Disposition 文件名 */
function parseFilename(disposition) {
  if (!disposition) return "";
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1].trim().replace(/^["']|["']$/g, ""));
    } catch (_) {
      return utf8Match[1];
    }
  }
  const normalMatch = /filename="?([^";]+)"?/i.exec(disposition);
  return normalMatch ? normalMatch[1].trim() : "";
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** 带鉴权头的 Blob 下载 */
async function downloadBlob(path, fallbackName) {
  const response = await request(path, { responseType: "blob" });
  const filename = parseFilename(response.headers.get("content-disposition")) || fallbackName || "download";
  const blob = await response.blob();
  if (!blob || blob.size === 0) throw new ApiError("下载内容为空，可能文件已丢失", 0);
  triggerDownload(blob, filename);
}

/* ------------------------------------------------------------------
 * 对外 API
 * ------------------------------------------------------------------ */
export const api = {
  /* ============ 认证 ============ */
  login(username, password) {
    return request("/auth/login", { method: "POST", body: { username, password } });
  },
  register(payload) {
    return request("/auth/register", { method: "POST", body: payload });
  },
  me() {
    return request("/auth/me");
  },
  changePassword(oldPassword, newPassword) {
    return request("/auth/change-password", {
      method: "POST",
      body: { old_password: oldPassword, new_password: newPassword },
    });
  },

  /* ============ 文件 ============ */
  async listFiles(params = {}) {
    const query = buildQuery(
      pick(params, [
        "page",
        "size",
        "keyword",
        "file_number",
        "file_name",
        "process_step",
        "process_code",
        "creator_id",
        "creator_name",
        "status",
        "upload_date_start",
        "upload_date_end",
        "sort",
        "order",
      ])
    );
    const data = await request("/files" + query);
    const page = normalizePage(data, { page: params.page, size: params.size });
    return { ...page, items: page.items.map(normalizeFile) };
  },
  async getFile(fileId) {
    return normalizeFile(await request(`/files/${encodeURIComponent(fileId)}`));
  },
  async listVersions(fileId) {
    const data = await request(`/files/${encodeURIComponent(fileId)}/versions`);
    const items = Array.isArray(data) ? data : normalizePage(data).items;
    return items.map((item) => {
      const uploader = item.uploader && typeof item.uploader === "object" ? item.uploader : null;
      return {
        ...item,
        _uploader: uploader ? uploader.real_name || uploader.username || "" : item.uploader_name || "",
        _size: item.file_size,
        _time: item.upload_time,
        _description: item.change_description || "",
      };
    });
  },
  async getApproval(fileId) {
    return normalizeApproval(await request(`/files/${encodeURIComponent(fileId)}/approval`));
  },
  async listSignatures(fileId) {
    const data = await request(`/files/${encodeURIComponent(fileId)}/signatures`);
    return Array.isArray(data) ? data : [];
  },
  uploadFile({ file, file_name, process_step, process_code, remarks, version }, onProgress) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("file_name", file_name);
    formData.append("process_step", process_step);
    if (process_code) formData.append("process_code", process_code);
    if (remarks) formData.append("remarks", remarks);
    if (version) formData.append("version", version);
    return uploadWithProgress("/files/upload", formData, { onProgress });
  },
  updateFile(fileId, fields, onProgress) {
    const formData = new FormData();
    if (fields.new_file) formData.append("new_file", fields.new_file);
    if (fields.file_name) formData.append("file_name", fields.file_name);
    if (fields.process_step) formData.append("process_step", fields.process_step);
    if (fields.process_code) formData.append("process_code", fields.process_code);
    if (fields.remarks !== undefined) formData.append("remarks", fields.remarks || "");
    if (fields.version_type) formData.append("version_type", fields.version_type);
    if (fields.change_description !== undefined) {
      formData.append("change_description", fields.change_description || "");
    }
    return uploadWithProgress(`/files/${encodeURIComponent(fileId)}`, formData, {
      method: "PUT",
      onProgress,
    });
  },
  submitReview(fileId, payload = {}) {
    return request(`/files/${encodeURIComponent(fileId)}/submit-review`, {
      method: "POST",
      body: payload,
    });
  },
  review(fileId, result, comment) {
    return request(`/files/${encodeURIComponent(fileId)}/review`, {
      method: "POST",
      body: { result, comment: comment || "" },
    });
  },
  approve(fileId, result, comment) {
    return request(`/files/${encodeURIComponent(fileId)}/approve`, {
      method: "POST",
      body: { result, comment: comment || "" },
    });
  },
  archive(fileId, comment) {
    return request(`/files/${encodeURIComponent(fileId)}/archive`, {
      method: "POST",
      body: { comment: comment || "" },
    });
  },
  deleteFile(fileId) {
    return request(`/files/${encodeURIComponent(fileId)}`, { method: "DELETE" });
  },
  /** 下载当前版本（可指定 version） */
  downloadFile(fileId, version) {
    const suffix = version ? "?version=" + encodeURIComponent(version) : "";
    return downloadBlob(`/files/${encodeURIComponent(fileId)}/download${suffix}`, "文件下载");
  },
  /** 下载指定历史版本：优先使用接口返回的 download_url */
  async downloadVersion(fileId, version) {
    if (version.download_url) return api.downloadByUrl(version.download_url, "版本下载");
    return downloadBlob(
      `/files/${encodeURIComponent(fileId)}/versions/${encodeURIComponent(version.version || "")}/download`,
      "版本下载"
    );
  },
  /** 按接口返回的相对地址下载（如 /api/files/1/download?version=V1.0.0） */
  downloadByUrl(url, fallbackName = "文件下载") {
    const path = String(url || "").replace(/^\/api/, "");
    if (!path) throw new ApiError("下载地址无效", 0);
    return downloadBlob(path, fallbackName);
  },

  /* ============ 待办审批 ============ */
  async pendingApprovals(type = "review", page = 1, size = 10, keyword = "") {
    const data = await request(
      `/approvals/pending${buildQuery({ type, page, size, keyword })}`
    );
    const result = normalizePage(data, { page, size });
    return {
      ...result,
      items: result.items.map((item) => {
        const file = item.file ? normalizeFile(item.file) : normalizeFile(item);
        const initiator = item.initiator && typeof item.initiator === "object" ? item.initiator : null;
        return {
          ...item,
          _file: file,
          _initiator: initiator ? initiator.real_name || initiator.username || "" : "",
          _submittedAt: item.submitted_at,
          _stepName: item.step_name || "",
          _flowId: item.flow_id,
        };
      }),
    };
  },
  /** 待归档：已批准（file_status=4）的文件列表 */
  async pendingArchive(page = 1, size = 10, keyword = "") {
    const result = await api.listFiles({ page, size, status: 4, keyword });
    return { ...result, items: result.items.map((file) => ({ _file: file })) };
  },

  /* ============ 文件清单 ============ */
  async getCatalog(params = {}) {
    const query = buildQuery(
      pick(params, ["page", "size", "keyword", "process_step", "snapshot_id", "sort", "order"])
    );
    const data = await request("/catalogs" + query);
    const page = normalizePage(data, { page: params.page, size: params.size });
    return {
      snapshot: normalizeSnapshot(data && data.snapshot),
      items: page.items.map(normalizeFile),
      total: page.total,
      page: page.page,
      size: page.size,
      pages: page.pages,
    };
  },
  refreshCatalog() {
    return request("/catalogs/refresh", { method: "POST" });
  },
  async listCatalogSnapshots(params = {}) {
    const data = await request("/catalogs/snapshots" + buildQuery(pick(params, ["page", "size", "refresh_type", "date_start", "date_end"])));
    return normalizePage(data, { page: params.page, size: params.size });
  },

  /* ============ 用户与角色 ============ */
  async listUsers(params = {}) {
    const data = await request(
      "/users" + buildQuery(pick(params, ["page", "size", "keyword", "is_active", "role", "sort", "order"]))
    );
    const page = normalizePage(data, { page: params.page, size: params.size });
    return {
      ...page,
      items: page.items.map((user) => ({
        ...user,
        _roles: Array.isArray(user.roles) ? user.roles : [],
      })),
    };
  },
  getUser(userId) {
    return request(`/users/${encodeURIComponent(userId)}`);
  },
  createUser(payload) {
    return request("/users", { method: "POST", body: payload });
  },
  updateUser(userId, payload) {
    return request(`/users/${encodeURIComponent(userId)}`, { method: "PUT", body: payload });
  },
  deleteUser(userId) {
    return request(`/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
  },
  setUserRoles(userId, roleIds) {
    return request(`/users/${encodeURIComponent(userId)}/roles`, {
      method: "PUT",
      body: { role_ids: roleIds },
    });
  },
  async listRoles() {
    const data = await request("/roles");
    return Array.isArray(data) ? data : normalizePage(data).items;
  },

  /* ============ 操作日志 ============ */
  async listLogs(params = {}) {
    const data = await request(
      "/logs" +
        buildQuery(
          pick(params, [
            "page",
            "size",
            "file_id",
            "operator_id",
            "operation_type",
            "target_type",
            "date_start",
            "date_end",
            "sort",
            "order",
          ])
        )
    );
    const page = normalizePage(data, { page: params.page, size: params.size });
    return {
      ...page,
      items: page.items.map((log) => {
        const operator = log.operator && typeof log.operator === "object" ? log.operator : null;
        return {
          ...log,
          _operator: operator ? operator.real_name || operator.username || "" : log.operator_name || "",
          _operatorId: operator ? operator.id : log.operator_id,
          _time: log.operation_time ?? log.created_at,
          _typeText: log.operation_type_text || log.operation_type || "",
          _details: log.operation_details || log.detail || "",
        };
      }),
    };
  },

  /* ============ 统计 ============ */
  getStats() {
    return request("/stats/overview");
  },
};
