/**
 * 用户管理（admin / user_manage）：列表、创建用户、启用禁用、角色分配
 * 契约：GET/POST /api/users、PUT /api/users/{id}、PUT /api/users/{id}/roles、GET /api/roles
 */
import { api } from "../api.js";
import { getCurrentUser } from "../auth.js";
import { escapeHtml, formatDateTime } from "../format.js";
import { roleLabel } from "../format.js";
import {
  bindPagination,
  confirmDialog,
  openModal,
  paginationHtml,
  showEmpty,
  showError,
  showLoading,
  toast,
  withButtonLoading,
} from "../ui.js";

const state = { page: 1, size: 10, keyword: "", is_active: "", role: "" };
let rolesCache = [];

export async function render(container) {
  await loadRoles();
  renderPage(container);
  await loadUsers(container);
}

async function loadRoles() {
  try {
    const roles = await api.listRoles();
    rolesCache = Array.isArray(roles) ? roles : [];
  } catch (_) {
    rolesCache = [];
  }
}

function roleOptions(selected, includeAll) {
  const options = [];
  if (includeAll) options.push('<option value="">全部角色</option>');
  rolesCache.forEach((role) => {
    const label = role.description || roleLabel(role.name) || role.name;
    options.push(
      `<option value="${escapeHtml(role.name)}" ${selected === role.name ? "selected" : ""}>${escapeHtml(label)}</option>`
    );
  });
  return options.join("");
}

function renderPage(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p class="page-desc">维护系统账号、启用状态与角色权限分配</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn btn-primary" id="btn-create-user">
          <svg class="icon"><use href="#icon-plus"/></svg><span>创建用户</span>
        </button>
      </div>
    </div>

    <div class="card">
      <form class="filter-form" id="user-filter" autocomplete="off">
        <div class="filter-field wide">
          <span class="field-label">关键字</span>
          <input class="input" name="keyword" maxlength="50" placeholder="工号 / 用户名 / 姓名" value="${escapeHtml(state.keyword)}">
        </div>
        <div class="filter-field">
          <span class="field-label">状态</span>
          <select class="select" name="is_active">
            <option value="" ${state.is_active === "" ? "selected" : ""}>全部状态</option>
            <option value="true" ${state.is_active === "true" ? "selected" : ""}>启用</option>
            <option value="false" ${state.is_active === "false" ? "selected" : ""}>禁用</option>
          </select>
        </div>
        <div class="filter-field">
          <span class="field-label">角色</span>
          <select class="select" name="role">${roleOptions(state.role, true)}</select>
        </div>
        <div class="filter-actions">
          <button type="submit" class="btn btn-primary">
            <svg class="icon"><use href="#icon-search"/></svg><span>查询</span>
          </button>
          <button type="button" class="btn" id="btn-reset-user-filter">重置</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">用户列表 <span class="count" id="user-count"></span></div>
        <div class="card-actions">
          <button type="button" class="btn btn-sm" id="btn-refresh-users">
            <svg class="icon"><use href="#icon-refresh"/></svg><span>刷新</span>
          </button>
        </div>
      </div>
      <div id="user-table-area"></div>
    </div>`;

  container.querySelector("#btn-create-user").addEventListener("click", () => openCreateModal(container));
  container.querySelector("#btn-refresh-users").addEventListener("click", () => loadUsers(container));

  const form = container.querySelector("#user-filter");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    state.keyword = String(formData.get("keyword") || "").trim();
    state.is_active = String(formData.get("is_active") || "");
    state.role = String(formData.get("role") || "");
    state.page = 1;
    loadUsers(container);
  });

  container.querySelector("#btn-reset-user-filter").addEventListener("click", () => {
    state.keyword = "";
    state.is_active = "";
    state.role = "";
    state.page = 1;
    form.reset();
    loadUsers(container);
  });
}

async function loadUsers(container) {
  const area = container.querySelector("#user-table-area");
  if (!area) return;
  showLoading(area);

  const params = { page: state.page, size: state.size };
  if (state.keyword) params.keyword = state.keyword;
  if (state.is_active !== "") params.is_active = state.is_active;
  if (state.role) params.role = state.role;

  try {
    const result = await api.listUsers(params);
    state.page = result.page || 1;
    state.size = result.size || state.size;
    const countEl = container.querySelector("#user-count");
    if (countEl) countEl.textContent = `共 ${result.total} 个账号`;
    renderTable(area, result, container);
  } catch (error) {
    const retry = showError(area, error.message || "用户列表加载失败");
    retry.addEventListener("click", () => loadUsers(container));
  }
}

function rolesHtml(user) {
  const roles = user._roles || [];
  if (!roles.length) return '<span style="color:#8f959e">—</span>';
  return roles
    .map((role) => {
      const label = role.description || roleLabel(role.name) || role.name || "—";
      return `<span class="badge badge-gray" title="${escapeHtml(role.name || "")}" style="margin-right:4px">${escapeHtml(label)}</span>`;
    })
    .join("");
}

function renderTable(area, result, container) {
  if (!result.items.length) {
    showEmpty(area, "暂无用户", "可点击右上角“创建用户”新增账号");
    return;
  }

  const currentUser = getCurrentUser();
  const rows = result.items
    .map((user) => {
      const isSelf = currentUser && user.id === currentUser.id;
      const active = Boolean(user.is_active);
      const toggleLabel = active ? "禁用" : "启用";
      const toggleTitle = isSelf && active ? 'title="不能禁用自己的账号"' : "";
      return `
        <tr>
          <td class="mono">${escapeHtml(user.employee_id || "—")}</td>
          <td class="cell-name">${escapeHtml(user.username || "—")}</td>
          <td>${escapeHtml(user.real_name || "—")}</td>
          <td>${escapeHtml(user.department || "—")}</td>
          <td>${escapeHtml(user.position || "—")}</td>
          <td>${rolesHtml(user)}</td>
          <td>${active ? '<span class="badge badge-green">启用</span>' : '<span class="badge badge-red">禁用</span>'}</td>
          <td class="col-num">${formatDateTime(user.last_login)}</td>
          <td class="col-actions">
            <button type="button" class="btn-text" data-action="roles" data-id="${escapeHtml(user.id)}" data-name="${escapeHtml(user.real_name || user.username || "")}">角色分配</button>
            <button type="button" class="btn-text ${active ? "danger" : ""}" data-action="toggle" data-id="${escapeHtml(user.id)}"
              data-active="${active ? "1" : "0"}" data-name="${escapeHtml(user.real_name || user.username || "")}"
              ${isSelf && active ? "disabled " + toggleTitle : ""}>${toggleLabel}</button>
          </td>
        </tr>`;
    })
    .join("");

  area.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>工号</th><th>用户名</th><th>姓名</th><th>部门</th><th>职位</th>
            <th>角色</th><th>状态</th><th>最后登录</th><th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
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
    loadUsers(container);
  });

  area.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      const userId = button.dataset.id;
      const name = button.dataset.name;
      if (button.dataset.action === "roles") {
        openRolesModal(container, userId, name);
        return;
      }
      toggleUser(container, userId, name, button.dataset.active === "1");
    });
  });
}

/* ---------------- 创建用户 ---------------- */
function roleCheckboxes(selectedIds = []) {
  if (!rolesCache.length) {
    return '<div class="form-tip">角色列表加载失败，可稍后在“角色分配”中设置。</div>';
  }
  return rolesCache
    .map(
      (role) => `
      <label class="check-item">
        <input type="checkbox" name="role_ids" value="${escapeHtml(role.id)}" ${selectedIds.includes(role.id) ? "checked" : ""}>
        <span>${escapeHtml(role.description || roleLabel(role.name) || role.name)}</span>
      </label>`
    )
    .join("");
}

function openCreateModal(container) {
  const modal = openModal({
    title: "创建用户",
    size: "md",
    content: `
      <form id="create-user-form" class="form-grid" autocomplete="off">
        <label class="field">
          <span class="field-label">工号<span class="required">*</span></span>
          <input class="input" name="employee_id" maxlength="20" placeholder="如 000101">
        </label>
        <label class="field">
          <span class="field-label">用户名<span class="required">*</span></span>
          <input class="input" name="username" maxlength="50" placeholder="登录账号">
        </label>
        <label class="field">
          <span class="field-label">姓名<span class="required">*</span></span>
          <input class="input" name="real_name" maxlength="50" placeholder="真实姓名">
        </label>
        <label class="field">
          <span class="field-label">初始密码<span class="required">*</span></span>
          <input class="input" name="password" type="password" maxlength="72" placeholder="6-72 位">
        </label>
        <label class="field">
          <span class="field-label">部门</span>
          <input class="input" name="department" maxlength="100" placeholder="选填，如 工艺部">
        </label>
        <label class="field">
          <span class="field-label">职位</span>
          <input class="input" name="position" maxlength="100" placeholder="选填，如 工艺员">
        </label>
        <div class="field span-2">
          <span class="field-label">角色</span>
          <div class="check-group">${roleCheckboxes()}</div>
        </div>
        <div class="field span-2">
          <label class="check-item"><input type="checkbox" name="is_active" checked><span>创建后立即启用</span></label>
        </div>
      </form>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-primary" data-action="ok">创建用户</button>`,
  });

  const form = modal.body.querySelector("#create-user-form");
  modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => modal.close());
  const okButton = modal.footer.querySelector('[data-action="ok"]');

  okButton.addEventListener("click", async () => {
    const values = {};
    ["employee_id", "username", "real_name", "password", "department", "position"].forEach((key) => {
      values[key] = String(form.elements[key].value || "").trim();
    });
    if (!values.employee_id) return toast("请输入工号", "error");
    if (!values.username) return toast("请输入用户名", "error");
    if (!values.real_name) return toast("请输入姓名", "error");
    if (!values.password) return toast("请输入初始密码", "error");
    if (values.password.length < 6 || values.password.length > 72) {
      return toast("密码长度需为 6-72 位", "error");
    }
    const roleIds = Array.from(form.querySelectorAll('input[name="role_ids"]:checked')).map((input) =>
      Number(input.value)
    );
    const payload = {
      employee_id: values.employee_id,
      username: values.username,
      password: values.password,
      real_name: values.real_name,
      is_active: form.elements.is_active.checked,
    };
    if (values.department) payload.department = values.department;
    if (values.position) payload.position = values.position;
    if (roleIds.length) payload.role_ids = roleIds;

    const restore = withButtonLoading(okButton, "创建中…");
    try {
      await api.createUser(payload);
      toast("用户创建成功", "success");
      modal.close();
      state.page = 1;
      await loadUsers(container);
    } catch (error) {
      toast(error.message || "创建用户失败", "error");
      restore();
    }
    return undefined;
  });
}

/* ---------------- 角色分配 ---------------- */
async function openRolesModal(container, userId, name) {
  let selectedRoleIds = [];
  try {
    const user = await api.getUser(userId);
    selectedRoleIds = (Array.isArray(user.roles) ? user.roles : [])
      .map((role) => Number(role.id))
      .filter((id) => !isNaN(id));
  } catch (error) {
    toast(error.message || "获取用户角色失败", "error");
    return;
  }

  const modal = openModal({
    title: "角色分配",
    size: "sm",
    content: `
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-tip">用户：${escapeHtml(name || "—")}。保存后将整体替换该用户的角色集合。</div>
        <div class="field">
          <span class="field-label">角色</span>
          <div class="check-group" id="role-checkboxes">${roleCheckboxes(selectedRoleIds)}</div>
        </div>
      </div>`,
    footer: `
      <button type="button" class="btn" data-action="cancel">取消</button>
      <button type="button" class="btn btn-primary" data-action="ok">保存</button>`,
  });

  modal.footer.querySelector('[data-action="cancel"]').addEventListener("click", () => modal.close());
  const okButton = modal.footer.querySelector('[data-action="ok"]');

  okButton.addEventListener("click", async () => {
    const roleIds = Array.from(modal.body.querySelectorAll('input[name="role_ids"]:checked')).map((input) =>
      Number(input.value)
    );
    const restore = withButtonLoading(okButton, "保存中…");
    try {
      await api.setUserRoles(userId, roleIds);
      toast("角色分配已更新", "success");
      modal.close();
      await loadUsers(container);
    } catch (error) {
      toast(error.message || "角色分配失败", "error");
      restore();
    }
  });
}

/* ---------------- 启用 / 禁用 ---------------- */
async function toggleUser(container, userId, name, active) {
  const nextActive = !active;
  const confirmed = await confirmDialog({
    title: nextActive ? "启用用户" : "禁用用户",
    message: nextActive
      ? `确定启用账号“${name || userId}”吗？`
      : `禁用后账号“${name || userId}”将无法登录，已签发的登录凭证立即失效。确定禁用吗？`,
    okText: nextActive ? "启用" : "禁用",
    danger: !nextActive,
  });
  if (!confirmed) return;
  try {
    await api.updateUser(userId, { is_active: nextActive });
    toast(nextActive ? "用户已启用" : "用户已禁用", "success");
    await loadUsers(container);
  } catch (error) {
    toast(error.message || "操作失败", "error");
  }
}
