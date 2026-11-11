/**
 * 全局常量配置（前端纯静态，无构建工具）
 * 接口路径与请求适配统一收敛在 api.js，本文件只放 UI 常量与存储键。
 */

export const API_BASE = "/api";

/** sessionStorage 键名（满足"token 存 sessionStorage"要求） */
export const TOKEN_KEY = "pms_token";
export const USER_KEY = "pms_user";

/** 分页默认值 */
export const DEFAULT_PAGE_SIZE = 10;
export const PAGE_SIZE_OPTIONS = [10, 20, 50];

/** 上传限制（与后端 MAX_FILE_SIZE / ALLOWED_EXTENSIONS 保持一致，仅做前端预校验） */
export const MAX_UPLOAD_SIZE = 50 * 1024 * 1024; // 50MB
export const ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"];

/** 角色中文名映射（角色 code 存 roles.name） */
export const ROLE_LABELS = {
  admin: "系统管理员",
  engineer: "工程师",
  leader: "组长",
  manager: "主管",
  archivist: "资料员",
};
