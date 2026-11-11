# Web 管理界面（纯静态，无构建、无外网依赖）

本目录是工艺文件管理系统的 Web 前端，由 FastAPI 以静态目录方式挂载到 `/ui`。
技术：原生 HTML + CSS + ES Module JS；不使用 npm、打包工具、外部 CDN 或外部字体。

## 1. 目录结构

```
web/
├── index.html          # 单页应用入口（登录页 + 主布局 + 内联 SVG 图标）
├── app.html            # 兼容入口（跳转到 index.html#/files，满 docs/API.md §8.3）
├── css/
│   └── style.css       # 全部样式（企业后台风格，适配 1366 宽度，含响应式）
├── js/
│   ├── app.js          # 应用入口：登录守卫、hash 路由、顶栏/侧边栏
│   ├── config.js       # 常量（API 前缀、分页、上传限制、角色中文名）
│   ├── format.js       # 转义/日期/文件大小/状态徽标/操作类型中文映射
│   ├── ui.js           # toast、弹窗、确认框、分页、空/加载/错误状态
│   ├── api.js          # 统一 API 适配层（fetch + Bearer + 错误解析 + 归一化 + 上传进度）
│   ├── auth.js         # sessionStorage token、当前用户、权限判断
│   ├── router.js       # 极简 hash 路由
│   ├── upload.js       # 上传校验、拖拽选择、进度条公共能力
│   └── views/
│       ├── login.js        # 登录
│       ├── dashboard.js    # 概览统计
│       ├── files.js        # 文件管理（检索/分页/上传/行操作）
│       ├── file-detail.js  # 文件详情（元数据/版本/审批时间线/签名/动作）
│       ├── approvals.js    # 待办审批（待审核/待批准/待归档）
│       ├── checklist.js    # 文件清单（快照/条目/手动刷新）
│       ├── users.js        # 用户管理（列表/创建/启禁用/角色分配）
│       └── logs.js         # 操作日志（分页/筛选）
└── README.md
```

## 2. 后端挂载方式

在 `main.py` 中（确保 `web/index.html` 存在后再挂载）：

```python
from fastapi import RedirectResponse
from fastapi.staticfiles import StaticFiles

app.mount("/ui", StaticFiles(directory="web", html=True), name="ui")

@app.get("/ui", include_in_schema=False)
async def ui_redirect():
    return RedirectResponse(url="/ui/")
```

- `html=True`：`/ui/` 返回 `web/index.html`。
- 前端使用相对路径引用 `css/`、`js/`，挂在任意子路径下均可工作。
- 所有接口请求走同源 `/api`，无需额外 CORS。

## 3. 路由（hash 单页）

| 路由 | 页面 | 权限 |
| --- | --- | --- |
| `#/login` | 登录 | 公开 |
| `#/dashboard` | 概览统计 | 登录用户 |
| `#/files` | 文件管理 | 登录用户（可见集合） |
| `#/files/:id` | 文件详情 | 文件可见用户 |
| `#/approvals` | 待办审批 | review / approve / archive 权限（按角色显示标签页） |
| `#/checklist` | 文件清单 | 登录用户；手动刷新需 catalog_manage |
| `#/users` | 用户管理 | admin（user_manage） |
| `#/logs` | 操作日志 | admin（user_manage） |

未登录访问任意页面自动跳转登录页；任意接口返回 401（或 403 `AUTH_USER_DISABLED`）会清理本地登录态并跳回登录页。

## 4. 已实现功能

- **登录**：用户名/密码、内联错误提示、登录按钮防重复提交；JWT 存 `sessionStorage`。
- **布局**：顶栏（系统名/当前用户/角色/退出）+ 侧边栏（概览、文件管理、待办审批、文件清单、用户管理、操作日志），按权限显示；待办数量徽标。
- **文件管理**：按文件名/编号/编制人/工序/状态/上传日期范围检索；分页；行操作（详情/下载/提交审核/删除，按权限与文件状态显示）。
- **上传**：弹窗表单（名称/工序/工序代码/版本/备注）、拖拽选择、前端后缀与 50MB 限制、XHR 真实进度条、按钮禁用防重复提交。
- **文件详情**：元数据、版本历史（逐版本下载）、审批流程时间线（环节/审批人/状态/签名时间/意见）、签名信息、历史流程折叠；提交审核、更新版本（major/minor/patch + 上传进度）、审核、批准、归档、删除。
- **待办审批**：待审核/待批准/待归档三标签，按权限显示；通过/驳回弹窗（驳回意见必填）；归档确认；操作后刷新列表与计数。
- **文件清单**：最新快照信息（编号/更新方式/时间/条目数/操作人）、条目表格、关键字检索、分页、下载；资料员/管理员可手动刷新快照。
- **用户管理**：列表（关键字/状态/角色筛选）、创建用户（角色多选）、启用/禁用、角色分配。
- **操作日志**：分页；按操作类型/操作人 ID/对象类型/日期范围筛选。
- **概览统计**：文件总数/待审核/待批准/已归档、状态分布、最近更新文件、最近操作。

## 5. 与 API 契约的对应

严格按 `docs/API.md`（v1.0 冻结）：

- 登录 `POST /api/auth/login`（JSON），Bearer token；`GET /api/auth/me` 的角色/权限用于按钮与导航控制。
- 分页统一 `{items,total,page,size,pages}`，参数 `page/size`。
- 文件状态使用 int 0-5 并展示 `file_status_text`；`allowed_actions` 控制详情页动作按钮。
- 审批动作：`POST /api/files/{id}/review|approve`，body `{result:"pass"|"reject", comment}`；`submit-review`、`archive` 同契约。
- 下载统一 `fetch` + `Authorization` + `blob`（不使用 `<a>` 直链），文件名取 `Content-Disposition`。
- 清单 `GET /api/catalogs`、`POST /api/catalogs/refresh`；用户/角色/日志/统计接口按契约。

### 契约差异与容错说明

- `docs/API.md §8.3` 提到主界面 `/ui/app.html`：本项目采用单页应用 + hash 路由，`index.html` 同时承载登录页与主界面；`app.html` 仅作兼容跳转。
- 状态/审批字段保留了少量别名容错（如 `status_label`、字符串枚举），便于后端灰度调整，不影响按契约正常工作。
- 若后端 `/api/auth/me` 未返回 `roles/permissions`，前端按“未知权限”放行非管理菜单，最终仍由后端鉴权；管理菜单（用户管理、操作日志）仍仅 admin 可见。

## 6. 本地联调

后端启动后（默认 `http://127.0.0.1:8000`）访问 `http://127.0.0.1:8000/ui/`。
种子账号见后端 `README.md` / `init_data.py`（密码不在前端代码中硬编码）。

浏览器要求：支持 ES Module 的现代浏览器（Chrome/Edge/Firefox/Safari 近三年版本）。
