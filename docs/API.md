# 工艺文件管理系统 API 契约（v1.0.3 冻结）

| 项 | 值 |
| --- | --- |
| 版本 | v1.0.3（2026-11-11 冻结，施工基线；历史见 §13） |
| 作者 | 项目经理（pm） |
| 依据 | docs/PLAN.md、工艺文件管理系统.md |
| 变更规则 | 任何路径/字段/错误码变更须 pm 更新本文并消息通知 backend/frontend/qa，禁止口头变更 |
| OpenAPI | 运行后 `/docs` 可查看自动生成文档（字段以本文为准） |

> 说明：本文所有示例均为**可直接对照实现**的契约；响应字段顺序无关，未标注"可选"的字段必须返回（无值用 `null`）。集合接口统一分页信封（§0.5），小集合例外（§0.5.3）。

---

## 0. 通用约定

### 0.1 基地址与协议

- Base URL：`http://127.0.0.1:8000`（以下路径均为完整路径，统一 `/api` 前缀，与现有实现一致）。
- 传输：HTTP/1.1，请求与响应均为 UTF-8 JSON；文件上传/下载为 `multipart/form-data` / 二进制流。
- 时间：响应时间字段统一 ISO 8601 UTC，形如 `2026-11-11T02:30:00+00:00`（SQLite 与 MySQL 一致口径）。
- 时区口径：日期型查询参数（`YYYY-MM-DD`）按业务时区 `CATALOG_TZ`（默认 `Asia/Shanghai`）解释，再转换为 UTC 区间；文件编号中的 `YYYYMM` 与清单快照号同样按业务时区生成；统计 `created_this_month` 按 UTC 月首计算。
- 分页参数：`page`（从 1 开始）、`size`（1-100，默认 10，越界钳制）。
- 排序参数：`sort` ∈ 白名单（见各接口），`order` ∈ `asc|desc`。
- 所有接口默认需要认证，除注明"公开"者。

### 0.2 认证

- 登录成功后携带请求头：
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```
- Token：JWT HS256，载荷 `{sub, uid, exp, iat}`；默认有效期 120 分钟（`ACCESS_TOKEN_EXPIRE_MINUTES`）。不做刷新令牌，过期需重新登录。
- 缺失/格式错误/签名错误 → 401 `AUTH_REQUIRED` / `AUTH_TOKEN_INVALID`；过期 → 401 `AUTH_TOKEN_EXPIRED`。
- 用户被禁用后，已签发 token 立即失效 → 403 `AUTH_USER_DISABLED`。
- 后端每请求查库加载角色与权限，权限变更立即生效。

### 0.3 统一成功响应

- 资源创建：HTTP 201，返回资源对象（不额外包一层）。
- 查询/更新/动作：HTTP 200，返回资源对象或动作结果对象。
- 删除/无返回动作：HTTP 200，返回 `{"message":"中文提示"}`（文件删除额外返回 `id`）。

### 0.4 统一错误响应

```
{
  "code": "FILE_LOCKED",
  "message": "审核中的文件禁止更新",
  "detail": null
}
```

- `code`：稳定错误码，前端判断逻辑用（§10 总表）。
- `message`：中文，可直接展示给用户。
- `detail`：可选，字段级校验错误时为 `{"field": "原因"}` 对象，其余为 `null`。
- `null` 语义（未产生/不适用/无权限）见 §9.4。
- 不返回堆栈与 SQL；500 仅 `{"code":"INTERNAL_ERROR","message":"服务器内部错误，请稍后重试","detail":null}`。

### 0.5 分页

#### 0.5.1 请求参数

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| page | int | 1 | 页码，≥1，越界返回空 items 但保留 total |
| size | int | 10 | 每页条数 1-100，越界钳制到 1/100 并回显 |
| sort | string | 见各接口 | 排序字段白名单，非法 → 422 VALIDATION_ERROR |
| order | string | desc | asc / desc |

#### 0.5.2 响应结构（所有分页集合）

```
{
  "items": [],
  "total": 0,
  "page": 1,
  "size": 10,
  "pages": 0
}
```

`pages = ceil(total/size)`，`total=0` 时 `pages=0`。

#### 0.5.3 例外（返回纯数组，不分页）

版本列表、签名列表、审批步骤、角色列表、权限列表、当前用户权限（这些集合天然很小）。API 各处已明确标注。

### 0.6 状态与枚举口径

#### 0.6.1 文件状态 file_status（int）

| 值 | 文本 file_status_text | 说明 |
| --- | --- | --- |
| 0 | 已删除 | 软删除，一律不返回 |
| 1 | 草稿 | 可编辑、可提交 |
| 2 | 待审核 | 组长审核中 |
| 3 | 待批准 | 主管批准中 |
| 4 | 已批准 | 待归档 |
| 5 | 已归档 | 进入文件清单 |

#### 0.6.2 审批流状态（int）

0 已终止（驳回）；1 进行中；2 已完成。

#### 0.6.3 审批步骤状态（int）

0 待处理；1 通过；2 驳回。

#### 0.6.4 版本更新类型 version_type

`major`（V(x+1).0.0）、`minor`（Vx.(y+1).0）、`patch`（Vx.y.(z+1)，默认）。

#### 0.6.5 操作日志类型 operation_type

upload、update、submit_review、review_pass、review_reject、approve_pass、approve_reject、archive、delete、download、login、register、change_password、user_create、user_update、user_disable、role_update、catalog_refresh。

#### 0.6.6 清单刷新方式 refresh_type

`manual`（手动）、`auto`（归档触发/每日 0 点）。

### 0.7 文件可见性（详情/下载/日志）

| 文件状态 | 可见用户 |
| --- | --- |
| 1 草稿 | 编制人（creator）、上传人（uploader）、admin、当前流程审批人 |
| 2/3 审批中 | 编制人、上传人、当前流程审批人、admin |
| 4/5 已批准/归档 | 所有登录用户 |
| 0 已删除 | 任何人（包括 admin）均不可见 |

不可见时统一返回 404 `FILE_NOT_FOUND`（避免通过 403 探测文件存在）。

### 0.8 下载方式

下载接口需要 `Authorization` 头，**不能**用 `<a href>` 直链（浏览器不会带 token）。前端用 `fetch` + `blob` 下载。响应头：

```
Content-Type: application/pdf
Content-Disposition: attachment; filename="CN-202611-0001_V1.0.0.pdf"; filename*=UTF-8''CN-202611-0001_V1.0.0.pdf
Content-Length: 12345
X-Content-Type-Options: nosniff
```

---

## 1. 认证（/api/auth）

### 1.1 POST /api/auth/login

- 权限：公开
- 说明：JSON 登录，成功后返回 JWT 与用户基础信息；记录 login 日志。
- 口令说明：示例中的 `<SEED_PASSWORD>` 等均为占位符，实际口令由环境变量注入；文档与示例不得出现真实口令。

请求：
```
{
  "username": "admin",
  "password": "<SEED_PASSWORD>"
}
```

响应 200：
```
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": {
    "id": 1,
    "employee_id": "000001",
    "username": "admin",
    "real_name": "系统管理员",
    "department": "信息部",
    "position": "系统管理员",
    "is_active": true,
    "roles": [{"id": 1, "name": "admin", "description": "系统管理员"}]
  }
}
```

错误：401 `AUTH_INVALID_CREDENTIALS`（用户名或密码错误）、403 `AUTH_USER_DISABLED`、422 `VALIDATION_ERROR`。

### 1.2 POST /api/auth/register

- 权限：公开（受配置开关 `ALLOW_REGISTER` 控制；生产默认 false → 403 `REGISTER_DISABLED`）
- 说明：自助注册，默认分配 engineer 角色；不开放角色自选。

请求：
```
{
  "employee_id": "000101",
  "username": "zhangsan",
  "password": "<初始密码>",
  "real_name": "张三",
  "department": "工艺部",
  "position": "工艺员"
}
```

响应 201：
```
{
  "id": 6,
  "employee_id": "000101",
  "username": "zhangsan",
  "real_name": "张三",
  "department": "工艺部",
  "position": "工艺员",
  "is_active": true,
  "roles": [{"id": 2, "name": "engineer", "description": "工艺员（编制）"}],
  "created_at": "2026-11-11T02:30:00+00:00"
}
```

错误：409 `DUPLICATE_USERNAME` / `DUPLICATE_EMPLOYEE_ID`、400 `PASSWORD_INVALID`（长度 6-72 字节）、403 `REGISTER_DISABLED`。

### 1.3 GET /api/auth/me

- 权限：登录用户
- 说明：返回当前用户信息、角色与权限码（前端按钮控制依据）。

响应 200：
```
{
  "id": 1,
  "employee_id": "000001",
  "username": "admin",
  "real_name": "系统管理员",
  "department": "信息部",
  "position": "系统管理员",
  "is_active": true,
  "roles": [{"id": 1, "name": "admin", "description": "系统管理员"}],
  "permissions": ["upload", "update", "delete", "review", "approve", "reject", "archive", "catalog_manage", "user_manage"],
  "last_login": "2026-11-11T02:29:00+00:00",
  "created_at": "2026-11-01T00:00:00+00:00"
}
```

### 1.4 POST /api/auth/change-password

- 权限：登录用户
- 说明：示例口令为占位符，实际值由用户输入；文档不得出现真实口令。

请求：
```
{
  "old_password": "<当前密码>",
  "new_password": "<新密码>"
}
```

响应 200：
```
{"message": "密码修改成功"}
```

错误：400 `INVALID_OLD_PASSWORD`、`SAME_PASSWORD`、`PASSWORD_INVALID`。

---

## 2. 用户与角色（/api/users、/api/roles、/api/permissions）

> 除 `GET /api/users/{id}` 允许本人访问外，本节接口均需 `user_manage` 权限（admin）。

### 2.1 GET /api/users

- 权限：user_manage
- 参数：`page`、`size`、`keyword`（工号/用户名/姓名模糊）、`is_active`（true/false）、`role`（角色名，如 engineer）、`sort` ∈ created_at/last_login/employee_id（默认 created_at desc）

响应 200：
```
{
  "items": [
    {
      "id": 2,
      "employee_id": "000002",
      "username": "engineer01",
      "real_name": "李工",
      "department": "工艺部",
      "position": "工艺员",
      "is_active": true,
      "roles": [{"id": 2, "name": "engineer", "description": "工艺员（编制）"}],
      "last_login": "2026-11-10T09:00:00+00:00",
      "created_at": "2026-11-01T00:00:00+00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 2.2 POST /api/users

- 权限：user_manage

请求：
```
{
  "employee_id": "000105",
  "username": "wangwu",
  "password": "<初始密码>",
  "real_name": "王五",
  "department": "工艺部",
  "position": "组长",
  "role_ids": [3],
  "is_active": true
}
```

响应 201：UserItem（结构同 2.1 items 元素）。
错误：409 `DUPLICATE_USERNAME` / `DUPLICATE_EMPLOYEE_ID`、404 `ROLE_NOT_FOUND`、400 `PASSWORD_INVALID`。

### 2.3 GET /api/users/{user_id}

- 权限：本人 或 user_manage
- 响应 200：UserItem；404 `USER_NOT_FOUND`。

### 2.4 PUT /api/users/{user_id}

- 权限：user_manage（本人修改资料走 `/api/auth/change-password`，不在此接口）
- 请求（字段均可选，只更新传入字段）：
```
{
  "real_name": "王五",
  "department": "技术部",
  "position": "主管",
  "is_active": true,
  "role_ids": [3, 4]
}
```

响应 200：UserItem。
错误：404 `USER_NOT_FOUND`、409 `CANNOT_DISABLE_SELF`（把自己 `is_active` 置 false）、409 `LAST_ADMIN_PROTECTED`（把最后一个启用 admin 禁用/移除 admin 角色）、404 `ROLE_NOT_FOUND`。

### 2.5 PUT /api/users/{user_id}/roles

- 权限：user_manage
- 说明：整体替换角色集合（传空数组 = 清空角色）。

请求：
```
{"role_ids": [3, 4]}
```

响应 200：UserItem。

### 2.6 DELETE /api/users/{user_id}

- 权限：user_manage
- 说明：软禁用（`is_active=false`），不删行、不清日志。

响应 200：
```
{"message": "用户已禁用", "id": 5}
```

错误：404 `USER_NOT_FOUND`、409 `CANNOT_DISABLE_SELF`、409 `LAST_ADMIN_PROTECTED`。

### 2.7 GET /api/roles

- 权限：user_manage
- 响应 200（纯数组）：
```
[
  {"id": 1, "name": "admin", "description": "系统管理员"},
  {"id": 2, "name": "engineer", "description": "工艺员（编制）"},
  {"id": 3, "name": "leader", "description": "组长（审核）"},
  {"id": 4, "name": "manager", "description": "主管（批准）"},
  {"id": 5, "name": "archivist", "description": "资料员（归档/清单）"}
]
```

### 2.8 GET /api/permissions

- 权限：user_manage
- 响应 200（纯数组）：
```
[
  {"id": 1, "code": "upload", "name": "上传", "description": "新建工艺文件"},
  {"id": 2, "code": "update", "name": "更新", "description": "修改文件/上传新版本"},
  {"id": 3, "code": "delete", "name": "删除", "description": "软删除文件"},
  {"id": 4, "code": "review", "name": "审核", "description": "审核环节通过/驳回"},
  {"id": 5, "code": "approve", "name": "批准", "description": "批准环节通过/驳回"},
  {"id": 6, "code": "reject", "name": "驳回", "description": "驳回动作"},
  {"id": 7, "code": "archive", "name": "归档", "description": "已批准文件归档"},
  {"id": 8, "code": "catalog_manage", "name": "清单管理", "description": "手动刷新文件清单"},
  {"id": 9, "code": "user_manage", "name": "用户管理", "description": "用户/角色管理与全量日志"}
]
```

---

## 3. 文件（/api/files）

### 3.0 文件对象定义

**FileItem**（列表元素）：
```
{
  "id": 1,
  "file_number": "CN-202611-0001",
  "file_name": "主轴加工工艺",
  "file_type": ".pdf",
  "process_code": "CN",
  "process_step": "车削",
  "version": "V1.0.0",
  "file_status": 5,
  "file_status_text": "已归档",
  "creator": {"id": 2, "real_name": "李工"},
  "uploader": {"id": 2, "real_name": "李工"},
  "initial_upload_time": "2026-11-10T01:00:00+00:00",
  "last_update_time": "2026-11-10T03:00:00+00:00",
  "file_size": 204800,
  "current_approver": null,
  "remarks": "首版"
}
```

**FileDetail** = FileItem + 以下字段：
```
{
  "version_count": 2,
  "latest_version": {
    "version": "V1.0.0",
    "upload_time": "2026-11-10T01:00:00+00:00",
    "change_description": "首版"
  },
  "approval": {
    "flow_id": 1,
    "status": 2,
    "status_text": "已完成",
    "current_step": 2,
    "current_step_name": "主管批准",
    "current_approver": null
  },
  "signatures": [
    {
      "id": 1,
      "step_type": "review",
      "step_name": "组长审核",
      "signer": {"id": 3, "real_name": "孙组长"},
      "signed_at": "2026-11-10T02:00:00+00:00",
      "remark": "工艺参数无误"
    }
  ],
  "allowed_actions": ["update", "delete", "archive"],
  "can_download": true
}
```

`allowed_actions` 由后端按"当前用户权限 + 资源状态 + 是否本人/审批人"实时计算，值域：`update/delete/submit_review/review/approve/archive`；无权限时为空数组。`approval` 无流程时为 `null`。

### 3.1 POST /api/files/upload

- 权限：upload
- Content-Type：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | binary | 是 | 文件本体，扩展名需在白名单（默认 .pdf/.doc/.docx/.xls/.xlsx/.txt），≤ MAX_FILE_SIZE（默认 50MB）；0 字节空文件拒绝（400 `FILE_EMPTY`） |
| file_name | string | 是 | 文件名称 1-255 字 |
| process_step | string | 是 | 工序名称 1-100 字 |
| process_code | string | 否 | 工序代码，`^[A-Z0-9]{2,4}$`，默认 `GEN` |
| version | string | 否 | `^V\d+\.\d+\.\d+$`，默认 V1.0.0 |
| remarks | string | 否 | ≤1000 字 |

响应 201：FileDetail（`file_status=1`，`file_number` 由服务端生成）。
错误：400 `FILE_TYPE_NOT_ALLOWED` / `VERSION_FORMAT_INVALID` / `FILE_NAME_DUPLICATED`（同工序代码下同名未删除文件）、413 `FILE_SIZE_EXCEEDED`、429 `RATE_LIMITED`、409 `FILE_NUMBER_CONFLICT`（重试耗尽）。
- 重名规则：同一 `process_code` 下**未删除**文件的文件名称唯一；比较前统一归一化（去首尾空白、连续空白压缩、英文大小写不敏感），由 `process_files.name_key` 唯一索引兜底；软删除后名称可复用；改名/升版同样校验；并发冲突返回 409 `FILE_NAME_DUPLICATED`。

### 3.2 GET /api/files

- 权限：登录用户（返回可见集合，见 §0.7）
- 说明：文件列表 + 多条件检索。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| keyword | string | 模糊匹配 file_name / file_number / process_step / 编制人姓名 |
| file_number | string | 编号模糊 |
| file_name | string | 名称模糊 |
| process_step | string | 工序模糊 |
| process_code | string | 工序代码精确 |
| creator_id | int | 编制人 ID |
| creator_name | string | 编制人姓名模糊 |
| status | string | 逗号分隔状态，如 `1,2` |
| upload_date_start | date | 首次上传日期起（含），YYYY-MM-DD；按业务时区（CATALOG_TZ，默认 Asia/Shanghai）解释 |
| upload_date_end | date | 首次上传日期止（含），YYYY-MM-DD；按业务时区解释，含当日整天 |
| page / size / sort / order | — | sort 白名单：last_update_time/initial_upload_time/file_number/file_name，默认 last_update_time desc |

响应 200：
```
{
  "items": [FileItem, ...],
  "total": 25,
  "page": 1,
  "size": 10,
  "pages": 3
}
```

### 3.3 GET /api/files/{file_id}

- 权限：文件可见（§0.7）
- 响应 200：FileDetail；404 `FILE_NOT_FOUND`。

### 3.4 PUT /api/files/{file_id}

- 权限：update +（本人 creator/uploader 或 admin）
- Content-Type：`multipart/form-data`；字段均可选：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| file_name | string | 新名称（1-255） |
| process_step | string | 新工序名称 |
| process_code | string | 新工序代码；**仅状态 1（草稿）允许修改**，状态 4/5 升版时传入不同值返回 400 VALIDATION_ERROR，状态 2/3 一律 409 FILE_LOCKED |
| remarks | string | 备注 |
| new_file | binary | 新版本文件 |
| version_type | string | major/minor/patch，默认 patch；**仅当传 new_file 时生效** |
| change_description | string | 变更说明（有 new_file 时建议必填，空则记"未填写"） |

规则：
- 状态 2/3（审核中）→ 409 `FILE_LOCKED`，审核中的文件禁止更新。
- 状态 4/5（已批准/已归档）→ 必须带 `new_file` 升版，处理后状态回 1（需重新审批）。
- 状态 1（草稿）→ 可只改元数据，也可升版。
- 元数据更新不改变版本号；带 `new_file` 时生成新版本记录 `(file_id, version)`，版本号按 version_type 递增。

响应 200：FileDetail。
错误：403 `FORBIDDEN`（非本人/无 update）、409 `FILE_LOCKED` / `STATE_CONFLICT` / `VERSION_EXISTS`、400 `VERSION_FORMAT_INVALID` / `NEW_FILE_REQUIRED`（已批准文件只传元数据未带新文件）、413 `FILE_SIZE_EXCEEDED`。

### 3.5 DELETE /api/files/{file_id}

- 权限：delete +（本人草稿/驳回态 或 admin）；状态 2/3 一律禁止（先驳回）
- 说明：软删除，`file_status=0`，记录 `deleted_at/deleted_by` 与 delete 日志；编号不复用。

响应 200：
```
{"message": "文件已删除", "id": 1}
```

错误：404 `FILE_NOT_FOUND`、403 `FORBIDDEN`、409 `FILE_LOCKED`（审核中禁止删除）。

### 3.6 GET /api/files/{file_id}/download

- 权限：文件可见（§0.7）
- 参数：`version`（可选，如 V1.0.0；缺省为当前版本）
- 响应 200：二进制流（头见 §0.8），并记录 download 日志。
- 错误：404 `FILE_NOT_FOUND` / `VERSION_NOT_FOUND` / `FILE_CONTENT_MISSING`（磁盘文件丢失）。

### 3.7 GET /api/files/{file_id}/versions

- 权限：文件可见
- 响应 200（纯数组，按 upload_time 倒序）：
```
[
  {
    "id": 2,
    "file_id": 1,
    "version": "V1.0.1",
    "file_size": 204900,
    "file_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "change_description": "修正页眉",
    "uploader": {"id": 2, "real_name": "李工"},
    "upload_time": "2026-11-10T03:00:00+00:00",
    "download_url": "/api/files/1/download?version=V1.0.1"
  }
]
```

### 3.8 GET /api/files/{file_id}/versions/{version}/download

- 权限：文件可见
- 响应 200：二进制流（指定历史版本）；404 `VERSION_NOT_FOUND`。

### 3.9 POST /api/files/{file_id}/submit-review

- 权限：update + 本人（creator/uploader）或 admin
- 前置：`file_status=1`，否则 409 `STATE_CONFLICT`
- 请求（字段均可选）：
```
{
  "reviewer_id": 3,
  "approver_id": 4,
  "comment": "请审核"
}
```
- 说明：未传 reviewer_id/approver_id 时自动分配（最早创建的具备 review/approve 权限的活跃用户）；审批针对当前版本。每次提交新建一条 flow。
- `comment`（提交说明）不单独落库，写入 `file_operation_logs.operation_details`（operation_type=`submit_review`）。

响应 200：
```
{
  "message": "已提交审核",
  "file_id": 1,
  "file_status": 2,
  "file_status_text": "待审核",
  "flow_id": 1,
  "version": "V1.0.0",
  "reviewer": {"id": 3, "real_name": "孙组长"},
  "approver": {"id": 4, "real_name": "赵主管"}
}
```

错误：403 `FORBIDDEN`、409 `STATE_CONFLICT` / `NO_ELIGIBLE_APPROVER`、404 `USER_NOT_FOUND`。

### 3.10 POST /api/files/{file_id}/review

- 权限：`result=pass` 时需 `review`；`result=reject` 时需 `reject`；且必须是该 flow 的步骤 1 审批人（`approver_id` 匹配）
- 前置：`file_status=2`
- 请求：
```
{"result": "pass", "comment": "工艺参数无误"}
```
- `result` ∈ `pass` / `reject`；拒绝时 `comment` 必填（≤500 字），通过时可选。
- 通过：文件 → 3（待批准），flow.current_step=2，写审核签名，分配主管为 current_approver；若预分配主管已被禁用/不存在，自动回退分配“最早创建的具备 approve 权限的活跃用户”，仍无则 409 `NO_ELIGIBLE_APPROVER`。
- 驳回：文件 → 1（草稿）并清空 current_approver，flow.status=0，写审核签名（含驳回意见）。
- 意见落库：写入 `approval_steps.approval_comment` 与 `file_signatures.remark`。
- 并发/幂等：审批步骤使用条件更新（`WHERE approval_status=0 AND step_number=1`）保证仅成功一次；步骤、签名、文件状态、flow 与日志在同一事务提交；重复/并发请求返回 409 `APPROVAL_ALREADY_DONE`。

响应 200（通过）：
```
{
  "message": "审核通过，已提交主管批准",
  "file_id": 1,
  "file_status": 3,
  "file_status_text": "待批准",
  "flow_id": 1,
  "next_approver": {"id": 4, "real_name": "赵主管"}
}
```

响应 200（驳回）：
```
{
  "message": "已驳回，文件退回草稿",
  "file_id": 1,
  "file_status": 1,
  "file_status_text": "草稿",
  "flow_id": 1,
  "next_approver": null
}
```

错误：403 `NOT_CURRENT_APPROVER` / `FORBIDDEN_PERMISSION`、409 `STATE_CONFLICT` / `APPROVAL_ALREADY_DONE`、400 `VALIDATION_ERROR`（驳回未填意见）。

### 3.11 POST /api/files/{file_id}/approve

- 权限：`result=pass` 时需 `approve`；`result=reject` 时需 `reject`；且必须是该 flow 步骤 2 审批人
- 前置：`file_status=3`
- 请求与响应同 3.10，通过后文件 → 4（已批准），flow.status=2 完成，写批准签名；`step2` 在**审核通过时**创建并分配主管；批准意见写入 `approval_steps.approval_comment` 与 `file_signatures.remark`；并发/幂等规则同 §3.10。
- 错误：同上（403 `NOT_CURRENT_APPROVER`、409 STATE_CONFLICT 等）。

响应 200（通过）：
```
{
  "message": "批准通过，可归档",
  "file_id": 1,
  "file_status": 4,
  "file_status_text": "已批准",
  "flow_id": 1,
  "next_approver": null
}
```

### 3.12 POST /api/files/{file_id}/archive

- 权限：archive（archivist/admin）
- 前置：`file_status=4`
- 请求（可选）：
```
{"comment": "资料室归档"}
```
- 副作用：状态 → 5、记录 archived_at/by、**自动生成清单快照**、写 archive 日志。
- `comment`（归档说明）不单独落库，写入 `file_operation_logs.operation_details`（operation_type=`archive`）。

响应 200：
```
{
  "message": "已归档，文件清单已更新",
  "file_id": 1,
  "file_status": 5,
  "file_status_text": "已归档",
  "archived_at": "2026-11-11T02:30:00+00:00",
  "snapshot": {
    "id": 12,
    "snapshot_no": "QD-20261111023000",
    "refresh_type": "auto",
    "item_count": 8,
    "created_at": "2026-11-11T02:30:00+00:00"
  }
}
```

错误：409 `STATE_CONFLICT`（非已批准）、403 `FORBIDDEN_PERMISSION`、404 `FILE_NOT_FOUND`。

### 3.13 GET /api/files/{file_id}/signatures

- 权限：文件可见
- 响应 200（纯数组，按 signed_at 升序）：
```
[
  {
    "id": 1,
    "file_id": 1,
    "version": "V1.0.0",
    "step_type": "review",
    "step_name": "组长审核",
    "signer": {"id": 3, "real_name": "孙组长"},
    "signer_name": "孙组长",
    "signature_text": "孙组长（组长）于 2026-11-10 10:00 审核通过",
    "signed_at": "2026-11-10T02:00:00+00:00",
    "remark": "工艺参数无误"
  },
  {
    "id": 2,
    "file_id": 1,
    "version": "V1.0.0",
    "step_type": "approve",
    "step_name": "主管批准",
    "signer": {"id": 4, "real_name": "赵主管"},
    "signer_name": "赵主管",
    "signature_text": "赵主管（主管）于 2026-11-10 11:00 批准通过",
    "signed_at": "2026-11-10T03:00:00+00:00",
    "remark": "同意"
  }
]
```

### 3.14 GET /api/files/{file_id}/approval

- 权限：文件可见 + 相关审批人 + admin
- 响应 200：
```
{
  "file_id": 1,
  "current_flow": {
    "id": 1,
    "file_id": 1,
    "version": "V1.0.0",
    "flow_type": "standard",
    "current_step": 2,
    "status": 2,
    "status_text": "已完成",
    "initiator": {"id": 2, "real_name": "李工"},
    "created_at": "2026-11-10T01:10:00+00:00",
    "completed_at": "2026-11-10T03:00:00+00:00",
    "reject_reason": null,
    "steps": [
      {
        "step_number": 1,
        "step_name": "组长审核",
        "approver": {"id": 3, "real_name": "孙组长"},
        "approval_status": 1,
        "approval_status_text": "通过",
        "approval_time": "2026-11-10T02:00:00+00:00",
        "approval_comment": "工艺参数无误"
      },
      {
        "step_number": 2,
        "step_name": "主管批准",
        "approver": {"id": 4, "real_name": "赵主管"},
        "approval_status": 1,
        "approval_status_text": "通过",
        "approval_time": "2026-11-10T03:00:00+00:00",
        "approval_comment": "同意"
      }
    ],
    "signatures": [...]
  },
  "history": [ ... 历史 flow 对象，结构同 current_flow ... ]
}
```

### 3.15 GET /api/files/{file_id}/logs

- 权限：文件可见者（编制人/上传人/审批人/admin）
- 参数：`page`、`size`
- 响应 200：分页 LogItem（结构见 §6）

---

## 4. 审批视图（/api/approvals）

### 4.1 GET /api/approvals/pending

- 权限：review 或 approve（按 type 校验；无对应权限 → 403 FORBIDDEN_PERMISSION）
- 说明：查询分配给当前用户的待处理步骤。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| type | string | all | review / approve / all（all 返回有权限的并集） |
| keyword | string | — | 文件名称/编号模糊 |
| page / size | — | 1 / 10 | |

响应 200：
```
{
  "items": [
    {
      "file": FileItem,
      "flow_id": 1,
      "step_number": 1,
      "step_name": "组长审核",
      "approval_status": 0,
      "submitted_at": "2026-11-10T01:10:00+00:00",
      "initiator": {"id": 2, "real_name": "李工"}
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 4.2 GET /api/approvals/flows

- 权限：登录用户（默认只返回当前用户可见文件对应的流程；user_manage 可看全部）
- 参数：`file_id`、`status`（0/1/2，逗号分隔）、`page`、`size`、`sort`（created_at，默认 desc）
- 响应 200：分页 FlowSummary：
```
{
  "items": [
    {
      "id": 1,
      "file_id": 1,
      "file_number": "CN-202611-0001",
      "file_name": "主轴加工工艺",
      "version": "V1.0.0",
      "current_step": 2,
      "status": 2,
      "status_text": "已完成",
      "initiator": {"id": 2, "real_name": "李工"},
      "created_at": "2026-11-10T01:10:00+00:00",
      "completed_at": "2026-11-10T03:00:00+00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 4.3 GET /api/approvals/flows/{flow_id}

- 权限：同 4.2
- 响应 200：单个 flow 对象（结构同 §3.14 `current_flow`）；404 `FLOW_NOT_FOUND`。

---

## 5. 文件清单（/api/catalogs）

### 5.0 对象定义

**CatalogSnapshot**：
```
{
  "id": 12,
  "snapshot_no": "QD-20261111023000",
  "refresh_type": "auto",
  "refresh_type_text": "自动",
  "operator": null,
  "item_count": 8,
  "created_at": "2026-11-11T02:30:00+00:00"
}
```

**CatalogItem**：
```
{
  "id": 101,
  "snapshot_id": 12,
  "file_id": 1,
  "file_number": "CN-202611-0001",
  "file_name": "主轴加工工艺",
  "version": "V1.0.0",
  "process_code": "CN",
  "process_step": "车削",
  "creator_id": 2,
  "creator_name": "李工",
  "file_size": 204800,
  "approved_at": "2026-11-10T03:00:00+00:00",
  "file_status": 5,
  "file_status_text": "已归档",
  "download_url": "/api/files/1/download?version=V1.0.0"
}
```

- `approved_at` 语义：**catalog_items 不存该列**，查询时由 `process_files.approved_at`（批准通过时写入）派生；历史数据缺失时回退 `process_files.archived_at`，仍无则为 `null`。状态 4（已批准未归档）条目该值应非空且等于批准通过时间。

### 5.1 GET /api/catalogs

- 权限：登录用户
- 说明：查询文件清单（默认最新快照；可通过 snapshot_id 查历史）。

参数：`page`、`size`（默认 10，最大 100，与全局分页一致）、`keyword`（编号/名称/工序模糊）、`process_step`、`snapshot_id`、`sort` ∈ file_number/approved_at（默认 file_number asc）。

响应 200：
```
{
  "snapshot": {
    "id": 12,
    "snapshot_no": "QD-20261111023000",
    "refresh_type": "auto",
    "refresh_type_text": "自动",
    "operator": null,
    "item_count": 8,
    "created_at": "2026-11-11T02:30:00+00:00"
  },
  "items": [CatalogItem, ...],
  "total": 8,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

无任何快照时：`snapshot: null`，items 空数组，total=0。

### 5.2 POST /api/catalogs/refresh

- 权限：catalog_manage（archivist/admin）
- 说明：立即生成新快照（全量重建：当前 4/5 状态且未删除的文件）；**同一秒内仅“相同刷新方式 + 相同操作人”的重复请求复用快照**（manual 与 auto 不得互相复用，避免归档同时刷新时返回 auto 快照）；快照号冲突时追加毫秒/序号后缀，保证每次语义正确的刷新都可见。

请求：无 body（或 `{}`）。

响应 200：
```
{
  "message": "文件清单已刷新",
  "snapshot": {
    "id": 13,
    "snapshot_no": "QD-20261111030000",
    "refresh_type": "manual",
    "refresh_type_text": "手动",
    "operator": {"id": 5, "real_name": "周资料员"},
    "item_count": 9,
    "created_at": "2026-11-11T03:00:00+00:00"
  }
}
```

错误：403 `FORBIDDEN_PERMISSION`、409 `REFRESH_IN_PROGRESS`（并发刷新锁占用，可重试）。

### 5.3 GET /api/catalogs/snapshots

- 权限：登录用户
- 参数：`page`、`size`、`refresh_type`（manual/auto）、`date_start`、`date_end`（YYYY-MM-DD）
- 响应 200：分页 CatalogSnapshot（items 元素为快照对象）。

### 5.4 GET /api/catalogs/snapshots/{snapshot_id}

- 权限：登录用户
- 响应 200：`{"snapshot": CatalogSnapshot, "items": [CatalogItem, ...]}`（该快照全部条目，不分页，条目数受控）
- 404 `CATALOG_NOT_FOUND`。

---

## 6. 操作日志（/api/logs）

### 6.1 GET /api/logs

- 权限：user_manage（admin 全量日志）；普通用户看单文件日志走 `/api/files/{id}/logs`
- 参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| page / size | — | 分页（默认 page=1、size=10，最大 100） |
| file_id | int | 文件 ID |
| operator_id | int | 操作人 |
| operation_type | string | 类型，逗号分隔多个 |
| target_type | string | file/user/auth/catalog |
| date_start / date_end | date | 操作日期区间（含当日）；按业务时区（CATALOG_TZ，默认 Asia/Shanghai）解释，与文件列表口径一致 |
| sort | string | operation_time（默认 desc） |

响应 200：
```
{
  "items": [
    {
      "id": 501,
      "file_id": 1,
      "target_type": "file",
      "target_id": 1,
      "operator": {"id": 3, "real_name": "孙组长"},
      "operation_type": "review_pass",
      "operation_type_text": "审核通过",
      "operation_time": "2026-11-10T02:00:00+00:00",
      "operation_details": "审核通过：主轴加工工艺 V1.0.0",
      "ip_address": "192.168.1.20"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20,
  "pages": 1
}
```

---

## 7. 统计（/api/stats）

### 7.1 GET /api/stats/overview

- 权限：登录用户
- 说明：概览数据；`users` 字段仅 user_manage 返回，其余用户为 `null`；`pending` 按当前用户权限与待办计算。

响应 200：
```
{
  "files": {
    "total": 42,
    "by_status": {
      "draft": 5,
      "pending_review": 3,
      "pending_approval": 2,
      "approved": 4,
      "archived": 28
    },
    "created_this_month": 12
  },
  "pending": {
    "my_review": 3,
    "my_approval": 2
  },
  "catalog": {
    "last_refresh_at": "2026-11-11T02:30:00+00:00",
    "last_snapshot_id": 12,
    "item_count": 8
  },
  "users": {
    "total": 6,
    "active": 6
  },
  "recent_operations": [
    {
      "id": 501,
      "operation_type": "archive",
      "operation_type_text": "归档",
      "operator": {"id": 5, "real_name": "周资料员"},
      "operation_time": "2026-11-11T02:30:00+00:00",
      "operation_details": "归档文件：主轴加工工艺"
    }
  ]
}
```

- `by_status` 键 ↔ 文件状态映射见 §9.3；统计不含已删除文件（file_status=0），`files.total` 为状态 1-5 之和；`null` 语义见 §9.4。

---

## 8. 系统

### 8.1 GET /

- 说明：`302` 重定向到 `/ui/`（前端登录页）。

### 8.2 GET /health

- 权限：公开
- 响应 200：
```
{"status": "healthy", "database": "ok", "version": "2.0.0"}
```
数据库不可用时 503：`{"status":"unhealthy","database":"error","version":"2.0.0"}`。

### 8.3 GET /ui/

- 说明：静态管理界面入口（`web/` 目录，login 页 `/ui/index.html`，主界面 `/ui/app.html`）。

---

## 9. 数据字典

### 9.1 公共对象

| 对象 | 字段 |
| --- | --- |
| UserBrief | id:int, employee_id:str, username:str, real_name:str, department:str?\|null, position:str?\|null |
| UserItem | UserBrief + is_active:bool, roles:Role[], last_login:datetime?\|null, created_at:datetime |
| Role | id:int, name:str（admin/engineer/leader/manager/archivist）, description:str?\|null |
| Permission | id:int, code:str, name:str, description:str?\|null |
| FileItem | 见 §3.0 |
| FileDetail | 见 §3.0 |
| VersionItem | id, file_id, version, file_size, file_hash, change_description, uploader:UserBrief, upload_time, download_url |
| SignatureItem | id, file_id, version, step_type, step_name, signer:UserBrief, signer_name, signature_text, signed_at, remark（signature_text 由后端按签名人首个内置角色中文名 + 业务时区时间生成，无角色时仅姓名） |
| ApprovalStepItem | step_number, step_name, approver:UserBrief, approval_status, approval_status_text, approval_time, approval_comment |
| ApprovalFlowDetail | id, file_id, version, flow_type, current_step, status, status_text, initiator:UserBrief, created_at, completed_at, reject_reason, steps:ApprovalStepItem[], signatures:SignatureItem[] |
| PendingItem | file:FileItem, flow_id, step_number, step_name, approval_status, submitted_at, initiator:UserBrief |
| CatalogSnapshot | id, snapshot_no, refresh_type, refresh_type_text, operator:UserBrief?\|null, item_count, created_at |
| CatalogItem | 见 §5.0；approved_at 由 process_files.approved_at 派生（缺失回退 archived_at） |
| LogItem | id, file_id:int?\|null, target_type, target_id, operator:UserBrief, operation_type, operation_type_text, operation_time, operation_details, ip_address |
| Page | items:array, total:int, page:int, size:int, pages:int |
| ErrorObject | code:str, message:str, detail:object?\|null |

### 9.2 文件详情 allowed_actions 取值

| 值 | 前端动作 | 后端条件 |
| --- | --- | --- |
| update | 更新/上传新版本 | update 权限 + 本人/admin + 状态 1（4/5 需带新文件） |
| delete | 删除 | delete 权限 + 本人草稿/admin + 状态非 2/3 |
| submit_review | 提交审核 | update 权限 + 本人/admin + 状态 1 |
| review | 审核 | review 权限 + 当前步骤 1 审批人 + 状态 2 |
| approve | 批准 | approve 权限 + 当前步骤 2 审批人 + 状态 3 |
| archive | 归档 | archive 权限 + 状态 4 |

### 9.3 统计 by_status 键映射

| by_status 键 | file_status | 中文 | 计入 files.total |
| --- | --- | --- | :-: |
| draft | 1 | 草稿 | ✓ |
| pending_review | 2 | 待审核 | ✓ |
| pending_approval | 3 | 待批准 | ✓ |
| approved | 4 | 已批准 | ✓ |
| archived | 5 | 已归档 | ✓ |
| deleted | 0 | 已删除 | ✗（不返回/固定 0） |

### 9.4 null 语义

`null` 表示"未产生/不适用/无权限查看"，前端按空值展示，不得当作 0 或空字符串：

- 时间类：`approved_at`（派生归档时间，状态 4 未归档为 null）、`archived_at`、`completed_at`、`approval_time` 未发生时均为 null。
- 关联对象：`current_approver`、`operator`、`next_approver`、`current_flow` 无对应对象时为 null。
- 权限遮挡：非 user_manage 用户的 `stats.users` 为 null。
- 数组字段（items/steps/signatures）无数据返回 `[]`，不返回 null。

---

## 10. 错误码总表

| code | HTTP | message（示例） | 触发场景 |
| --- | --- | --- | --- |
| VALIDATION_ERROR | 422 | 请求参数校验失败 | 字段缺失/类型错误/格式错误；detail 含字段原因 |
| AUTH_REQUIRED | 401 | 请先登录 | 缺少 Authorization 头 |
| AUTH_TOKEN_INVALID | 401 | 登录凭证无效 | 签名/格式错误 |
| AUTH_TOKEN_EXPIRED | 401 | 登录已过期，请重新登录 | exp 过期 |
| AUTH_INVALID_CREDENTIALS | 401 | 用户名或密码错误 | 登录失败 |
| AUTH_USER_DISABLED | 403 | 用户已被禁用 | 禁用用户登录或携旧 token |
| REGISTER_DISABLED | 403 | 系统未开放自助注册 | ALLOW_REGISTER=false |
| FORBIDDEN | 403 | 无权执行该操作 | 资源级校验失败（非本人） |
| FORBIDDEN_PERMISSION | 403 | 缺少权限：review | RBAC 权限缺失，detail 含权限码 |
| USER_NOT_FOUND | 404 | 用户不存在 | — |
| DUPLICATE_USERNAME | 409 | 用户名已存在 | 创建/注册 |
| DUPLICATE_EMPLOYEE_ID | 409 | 工号已存在 | 创建/注册 |
| PASSWORD_INVALID | 400 | 密码长度需为 6-72 字节 | 注册/改密/建用户 |
| INVALID_OLD_PASSWORD | 400 | 当前密码错误 | 改密 |
| SAME_PASSWORD | 400 | 新密码不能与当前密码相同 | 改密 |
| CANNOT_DISABLE_SELF | 409 | 不能禁用自己的账号 | 用户管理 |
| LAST_ADMIN_PROTECTED | 409 | 系统至少保留一个启用的管理员 | 用户管理 |
| ROLE_NOT_FOUND | 404 | 角色不存在 | 角色分配 |
| FILE_NOT_FOUND | 404 | 文件不存在 | 不存在/已删除/不可见 |
| VERSION_NOT_FOUND | 404 | 文件版本不存在 | 指定版本下载 |
| FILE_CONTENT_MISSING | 404 | 文件内容缺失，请联系管理员 | 磁盘文件丢失 |
| FILE_TYPE_NOT_ALLOWED | 400 | 不支持的文件类型：.exe | 上传扩展名白名单 |
| FILE_EMPTY | 400 | 不能上传空文件 | 上传 0 字节文件 |
| FILE_SIZE_EXCEEDED | 413 | 文件大小超过限制（50MB） | 上传超限 |
| FILE_NAME_DUPLICATED | 409 | 同一工序代码下已存在同名文件（忽略大小写/首尾空白） | 上传/改名；软删除后名称可复用 |
| FILE_NUMBER_CONFLICT | 409 | 文件编号生成冲突，请重试 | 编号重试耗尽 |
| FILE_LOCKED | 409 | 审核中的文件禁止更新/删除 | 状态 2/3 更新或删除 |
| STATE_CONFLICT | 409 | 当前状态为待审核，不可执行批准 | 状态机非法迁移 |
| VERSION_FORMAT_INVALID | 400 | 版本号格式应为 Vx.y.z | 上传/更新 |
| VERSION_EXISTS | 409 | 该版本号已存在 | 升版冲突 |
| NEW_FILE_REQUIRED | 400 | 已批准/已归档文件更新必须上传新文件 | 状态 4/5 只改元数据 |
| NOT_FILE_OWNER | 403 | 只能操作本人创建的文件 | 资源级校验 |
| NOT_CURRENT_APPROVER | 403 | 您不是该步骤的审批人 | 审核/批准越权 |
| NO_ELIGIBLE_APPROVER | 409 | 未找到可用的审批人，请联系管理员 | 自动分配失败 |
| FLOW_NOT_FOUND | 404 | 审批流程不存在 | 流程查询 |
| APPROVAL_ALREADY_DONE | 409 | 该审批步骤已处理 | 重复审核/批准 |
| CATALOG_NOT_FOUND | 404 | 文件清单不存在 | 指定快照查询 |
| REFRESH_IN_PROGRESS | 409 | 清单正在刷新，请稍后重试 | 并发手动刷新 |
| RATE_LIMITED | 429 | 操作过于频繁，请稍后再试 | 上传冷却 |
| INTERNAL_ERROR | 500 | 服务器内部错误，请稍后重试 | 未捕获异常 |

---

## 11. 接口-权限矩阵

| 方法 | 路径 | 权限/角色 | 说明 |
| --- | --- | --- | --- |
| POST | /api/auth/login | 公开 | 登录 |
| POST | /api/auth/register | 公开（开关） | 注册，默认 engineer |
| GET | /api/auth/me | 登录 | 当前用户 |
| POST | /api/auth/change-password | 登录 | 改密 |
| GET | /api/users | user_manage | 用户列表 |
| POST | /api/users | user_manage | 建用户 |
| GET | /api/users/{id} | 本人 / user_manage | 用户详情 |
| PUT | /api/users/{id} | user_manage | 改用户 |
| PUT | /api/users/{id}/roles | user_manage | 分配角色 |
| DELETE | /api/users/{id} | user_manage | 禁用用户 |
| GET | /api/roles | user_manage | 角色列表 |
| GET | /api/permissions | user_manage | 权限列表 |
| POST | /api/files/upload | upload | 上传 |
| GET | /api/files | 登录（可见集合） | 列表/检索 |
| GET | /api/files/{id} | 可见 | 详情 |
| PUT | /api/files/{id} | update + 本人/admin | 更新/升版 |
| DELETE | /api/files/{id} | delete + 本人/admin | 软删除 |
| GET | /api/files/{id}/download | 可见 | 下载 |
| GET | /api/files/{id}/versions | 可见 | 版本列表 |
| GET | /api/files/{id}/versions/{v}/download | 可见 | 版本下载 |
| POST | /api/files/{id}/submit-review | update + 本人/admin | 提交审核 |
| POST | /api/files/{id}/review | review（通过）/ reject（驳回）+ 当前步骤审批人 | 审核 |
| POST | /api/files/{id}/approve | approve（通过）/ reject（驳回）+ 当前步骤审批人 | 批准 |
| POST | /api/files/{id}/archive | archive | 归档 |
| GET | /api/files/{id}/signatures | 可见 | 签名 |
| GET | /api/files/{id}/approval | 可见 + 审批人 + admin | 流程 |
| GET | /api/files/{id}/logs | 可见（本人/审批人/admin） | 文件日志 |
| GET | /api/approvals/pending | review / approve | 我的待办 |
| GET | /api/approvals/flows | 登录（可见范围） | 流程列表 |
| GET | /api/approvals/flows/{id} | 登录（可见范围） | 流程详情 |
| GET | /api/catalogs | 登录 | 清单查询 |
| POST | /api/catalogs/refresh | catalog_manage | 手动刷新 |
| GET | /api/catalogs/snapshots | 登录 | 快照历史 |
| GET | /api/catalogs/snapshots/{id} | 登录 | 快照详情 |
| GET | /api/logs | user_manage | 全量日志 |
| GET | /api/stats/overview | 登录 | 概览 |
| GET | /health | 公开 | 健康检查 |

---

## 12. 附录：全流程 curl 示例

```
BASE=http://127.0.0.1:8000

# 前置：口令一律从环境变量注入，禁止在示例/文档中写真实值
: "${ADMIN_PASSWORD:?请先 export ADMIN_PASSWORD（取值见 SEED_PASSWORD）}"

# 1) 登录（admin）
TOKEN=$(curl -s -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

AUTH="Authorization: Bearer $TOKEN"

# 2) 我的信息
curl -s $BASE/api/auth/me -H "$AUTH"

# 3) 上传工艺文件（engineer01 登录略）
curl -s -X POST $BASE/api/files/upload -H "$AUTH" \
  -F "file=@./样例工艺.pdf" \
  -F "file_name=主轴加工工艺" -F "process_step=车削" -F "process_code=CN" \
  -F "remarks=首版" 

# 4) 列表检索（按编制人/日期/工序/状态）
curl -s "$BASE/api/files?keyword=主轴&process_step=车削&status=1,2&page=1&size=10" -H "$AUTH"

# 5) 提交审核（文件 1）
curl -s -X POST $BASE/api/files/1/submit-review -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"comment":"请审核"}'

# 6) leader01 登录后审核通过
curl -s -X POST $BASE/api/files/1/review -H "$AUTH_LEADER" \
  -H "Content-Type: application/json" -d '{"result":"pass","comment":"工艺参数无误"}'

# 7) manager01 登录后批准通过
curl -s -X POST $BASE/api/files/1/approve -H "$AUTH_MANAGER" \
  -H "Content-Type: application/json" -d '{"result":"pass","comment":"同意"}'

# 8) archivist01 登录后归档（返回 snapshot）
curl -s -X POST $BASE/api/files/1/archive -H "$AUTH_ARCHIVIST" \
  -H "Content-Type: application/json" -d '{"comment":"资料室归档"}'

# 9) 查看文件清单
curl -s "$BASE/api/catalogs?page=1&size=20" -H "$AUTH"

# 10) 下载当前版本（保存文件）
curl -s -L "$BASE/api/files/1/download" -H "$AUTH" -o ./下载_CN-202611-0001.pdf

# 11) 手动刷新清单（archivist/admin）
curl -s -X POST "$BASE/api/catalogs/refresh" -H "$AUTH_ARCHIVIST"

# 12) 待办、统计、日志
curl -s "$BASE/api/approvals/pending?type=review" -H "$AUTH_LEADER"
curl -s "$BASE/api/stats/overview" -H "$AUTH"
curl -s "$BASE/api/logs?page=1&size=20" -H "$AUTH"
```

---

## 13. 变更记录

| 版本 | 日期 | 变更 | 作者 |
| --- | --- | --- | --- |
| v1.0 | 2026-11-11 | 初版冻结：认证、用户/角色、文件、审批、清单、日志、统计、错误码与全流程示例 | pm |
| v1.0.2 | 2026-11-11 | P0/P1 修订：①文档口令全部改占位符（`<SEED_PASSWORD>` 等），真实口令仅由环境变量注入；②补字段溯源：审核/批准意见→approval_steps.approval_comment+file_signatures.remark，提交/归档说明→operation_details，CatalogItem.approved_at 改为由 process_files.archived_at 派生；③重名规则（同 process_code+未删除+归一化，name_key 唯一索引兜底）；④审批并发/幂等（条件更新、单事务、409 APPROVAL_ALREADY_DONE）；⑤reject 权限分支校验；⑥分页统一默认 size=10、null 语义与 by_status 映射写入数据字典。提出人：Lead/chief | pm |
| v1.0.3 | 2026-11-11 | 二轮澄清：①CatalogItem.approved_at 派生源改为 process_files.approved_at（归档前状态 4 也有值），缺失回退 archived_at；②快照复用仅限“相同刷新方式+操作人”，manual/auto 不互相复用；③0 字节空文件拒绝（新增 FILE_EMPTY 400）；④完成态流程 current_approver 示例修正为 null；⑤审核通过时预分配主管失效则回退自动分配。提出人：Lead/评审 | pm |
