# 工艺文件管理系统（ProcessMS）

面向工艺部门的工艺文件全生命周期管理平台：编制上传 → 组长审核 → 主管批准 → 资料员归档 → 自动/手动更新文件清单 → 按文件名/编号/编制人/工序检索 → 全流程审计留痕。

- 后端：FastAPI + SQLAlchemy 2.0（全异步）+ MySQL 8（生产）/ SQLite（开发测试）
- 前端：纯静态 HTML/CSS/JS（web/，无构建链），由后端挂载在 /ui/
- 接口契约：[docs/API.md](docs/API.md)；实施计划：[docs/PLAN.md](docs/PLAN.md)
- 当前版本：2.0.0

---

## 1. 功能特性

| 模块 | 能力 |
| --- | --- |
| 认证 | JWT（PyJWT，HS256，默认 120 分钟）、登录/注册/当前用户/修改密码、禁用用户旧令牌即时失效 |
| RBAC | 5 角色、9 权限、角色权限矩阵、资源级校验（本人/审批人/管理员）、接口级 403 |
| 文件 | 上传（类型/大小/空文件校验、2 秒冷却）、列表与多条件检索分页、详情、更新升版、软删除、受控下载 |
| 编号 | `工序代码-YYYYMM-4位流水号`（如 `CN-202611-0001`），序列表 + 唯一索引 + 冲突重试 |
| 版本 | `Vx.y.z`，major/minor/patch 递增；审核中（状态 2/3）锁定；历史版本可追溯/可下载 |
| 审批 | 提交审核、组长审核、主管批准、驳回、归档；审批流/步骤/签名落库；待办、流程与签名查询 |
| 文件清单 | 快照式清单（快照 + 条目两步存储）；归档自动刷新、手动刷新、每日 0 点自动刷新（可配置） |
| 审计 | 上传/更新/提交/审核/批准/归档/删除/下载/登录/用户管理等操作日志，支持筛选分页 |
| 统计 | 文件状态分布、我的待办、清单最近刷新、最近操作、用户统计（管理员） |
| 安全 | 密码 bcrypt 直连、上传目录不静态暴露、下载鉴权 + 路径穿越防护 + RFC 5987 文件名、LIKE 转义、CORS 白名单 |

---

## 2. 目录结构

```
ProcessMS/
├── main.py                 # FastAPI 应用入口：lifespan 初始化、异常处理、路由注册、/ui 挂载
├── config.py               # pydantic-settings 配置（环境变量 / .env）
├── database.py             # 异步引擎、AsyncSession、Base、get_db、init_db
├── init_data.py            # 异步幂等种子：5 角色 / 9 权限 / 演示账号
├── run.py                  # 本地启动脚本
├── models/                 # ORM：用户、文件、审批、清单
├── schemas/                # Pydantic v2 请求模型
├── crud/                   # 数据访问（只 flush，不 commit）
├── services/               # 服务层入口：审批状态机、清单、调度
├── routers/                # /api 路由
├── dependencies/           # 认证与权限依赖
├── utils/                  # 安全、时间、编号、版本、上传、分页、序列化等
├── web/                    # 纯静态管理界面（frontend 提供）
├── tests/                  # pytest 自动化测试（qa 提供）
├── docs/                   # PLAN.md / API.md / REVIEW.md
├── uploads/                # 上传文件（运行时生成，gitignore）
├── data/                   # SQLite 数据库（运行时生成，gitignore）
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

---

## 3. 快速开始（SQLite，零配置）

环境要求：Python 3.10+（推荐 3.12），Windows/Linux/macOS 均可。

```bash
cd ProcessMS

# 1) 创建虚拟环境并安装依赖
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2) 准备配置：复制示例文件，并修改 SECRET_KEY 与 SEED_PASSWORD
#    Windows: copy .env.example .env
#    Linux/macOS: cp .env.example .env
#    - SECRET_KEY：至少 32 位随机字符串（生产必须修改）
#    - SEED_PASSWORD：自行设定的演示账号初始口令（仅开发/演示环境使用）
#    - DATABASE_URL 默认 sqlite+aiosqlite:///./data/processms.db，无需安装数据库

# 3) 启动
python run.py
# 等价于：uvicorn main:app --host 127.0.0.1 --port 8000
```

启动后：

- 管理界面：<http://127.0.0.1:8000/ui/>
- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

首次启动会自动建表并写入 5 角色 / 9 权限 / 角色权限矩阵；若 `SEED_PASSWORD` 已设置且 `ENV=dev` 或 `SEED_DEMO_USERS=true`，还会创建演示账号：

| 用户名 | 姓名 | 角色 |
| --- | --- | --- |
| admin | 系统管理员 | admin |
| engineer01 | 李工 | engineer（工艺员） |
| leader01 | 孙组长 | leader（组长） |
| manager01 | 赵主管 | manager（主管） |
| archivist01 | 周资料员 | archivist（资料员） |

> 演示账号初始口令统一取环境变量 `SEED_PASSWORD`，代码与文档不内置默认口令；未设置时不会创建演示账号（仅初始化角色权限）。

---

## 4. 生产部署（MySQL 8）

1. 创建数据库（utf8mb4）：

```sql
CREATE DATABASE process_file_system DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'processms'@'%' IDENTIFIED BY '<数据库口令>';
GRANT ALL PRIVILEGES ON process_file_system.* TO 'processms'@'%';
FLUSH PRIVILEGES;
```

2. 生产环境变量（示例，口令一律走环境变量，不要写进代码）：

```ini
ENV=prod
DATABASE_URL=mysql+aiomysql://processms:<数据库口令>@127.0.0.1:3306/process_file_system?charset=utf8mb4
SECRET_KEY=<至少32位随机字符串>
ALLOW_REGISTER=false
SEED_DEMO_USERS=false
SEED_PASSWORD=
ENABLE_SCHEDULER=true
CATALOG_TZ=Asia/Shanghai
UPLOAD_DIR=/var/lib/processms/uploads
ALLOWED_ORIGINS=https://your-domain.example.com
```

3. 启动（单 worker，调度器进程内运行）：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

注意事项：

- 生产环境若仍使用默认开发 `SECRET_KEY`，应用会拒绝启动；`ENV=prod` 时强制关闭自助注册。
- `ENABLE_SCHEDULER=true` 的每日清单刷新是进程内任务，**多 worker 部署时只能有一个实例开启**，否则请仅保留一个 worker 或改为外部定时任务。
- 表结构在启动时通过 `create_all` 自动创建；本轮不引入 Alembic 迁移。
- `uploads/` 必须挂载持久卷；数据库需定期备份。

---

## 5. Docker / Docker Compose

```bash
# 在 ProcessMS 目录执行；先在 shell 或 .env 中设置 SECRET_KEY（以及可选的 MySQL 口令）
docker compose up --build -d
# 管理界面 http://127.0.0.1:8000/ui/ ，接口文档 /docs
```

`docker-compose.yml` 包含 MySQL 8 与应用两个服务，应用以非 root 用户运行，上传目录挂载命名卷；数据库口令与 `SECRET_KEY` 均通过环境变量注入，请勿使用示例值。生产请在前面加反向代理并启用 HTTPS。

---

## 6. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENV` | `dev` | `dev` / `prod`；prod 缺少自定义 SECRET_KEY 拒绝启动、强制关闭自助注册 |
| `DEBUG` | `true` | 调试开关 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址与端口 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/processms.db` | SQLAlchemy 异步连接串；生产用 `mysql+aiomysql://...` |
| `SECRET_KEY` | 开发占位值 | JWT 签名密钥，生产必须设置 ≥32 位随机串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | 令牌有效期（分钟） |
| `ALLOW_REGISTER` | `false` | 是否开放自助注册（开发环境可在 .env 设 true） |
| `UPLOAD_DIR` | `uploads` | 上传根目录（可绝对路径） |
| `MAX_FILE_SIZE` | `52428800` | 单文件大小上限（字节，默认 50MB） |
| `ALLOWED_EXTENSIONS` | `.pdf,.doc,.docx,.xls,.xlsx,.txt` | 扩展名白名单（逗号分隔） |
| `UPLOAD_COOLDOWN_SECONDS` | `2` | 同一用户上传冷却秒数（0 表示关闭） |
| `DEFAULT_PROCESS_CODE` | `GEN` | 未传 process_code 时的默认工序代码 |
| `ENABLE_SCHEDULER` | `true` | 是否启用每日清单自动刷新 |
| `CATALOG_TZ` | `Asia/Shanghai` | 业务时区（清单快照号/每日 0 点/日期筛选口径） |
| `CATALOG_REFRESH_HOUR` | `0` | 每日自动刷新小时 |
| `CATALOG_REFRESH_ON_STARTUP` | `false` | 启动时是否立即刷新一次清单 |
| `ALLOWED_ORIGINS` | localhost 相关地址 | CORS 白名单（逗号分隔或 JSON 数组） |
| `WEB_DIR` | `web` | 前端静态目录（存在时挂载 /ui） |
| `SEED_DEMO_USERS` | `false` | 是否创建演示账号（ENV=dev 时默认启用） |
| `SEED_PASSWORD` | 空 | 演示账号初始口令；为空则不创建演示账号 |

完整示例见 [.env.example](.env.example)，其中口令均为占位符。

---

## 7. 角色与权限矩阵

权限码：`upload` / `update` / `delete` / `review` / `approve` / `reject` / `archive` / `catalog_manage` / `user_manage`

| 角色 | 上传 | 更新 | 删除 | 审核 | 批准 | 驳回 | 归档 | 清单管理 | 用户管理 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| admin 系统管理员 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| engineer 工艺员 | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| leader 组长 | ✓ | ✓ |  | ✓ |  | ✓ |  |  |  |
| manager 主管 |  |  |  |  | ✓ | ✓ |  |  |  |
| archivist 资料员 |  |  |  |  |  |  | ✓ | ✓ |  |

- 一个用户可拥有多角色，权限取并集；admin 权限检查短路放行。
- 资源级限制：提交/更新/删除要求本人（creator/uploader）或 admin；审核/批准必须是当前步骤审批人；审核中（状态 2/3）禁止更新/删除。

---

## 8. 业务规则摘要

### 8.1 文件状态机（file_status int）

| 值 | 状态 | 可执行动作 |
| --- | --- | --- |
| 0 | 已删除 | 软删除后不可见，编号不复用 |
| 1 | 草稿 | 更新、提交审核、本人删除 |
| 2 | 待审核 | 组长审核（通过 → 3 / 驳回 → 1） |
| 3 | 待批准 | 主管批准（通过 → 4 / 驳回 → 1） |
| 4 | 已批准 | 归档（→ 5）或带新文件升版（→ 1 重新审批） |
| 5 | 已归档 | 带新文件升版（→ 1 重新审批） |

审批流状态：0 已终止 / 1 进行中 / 2 已完成；步骤状态：0 待处理 / 1 通过 / 2 驳回。
非法流转统一返回 409（`STATE_CONFLICT` / `FILE_LOCKED` / `APPROVAL_ALREADY_DONE`），并做条件更新保证并发幂等。

### 8.2 编号与版本

- 编号：`{process_code}-{YYYYMM}-{NNNN}`，YYYYMM 取业务时区首次上传年月；序列表 `file_number_sequences` 原子自增 + `file_number` 唯一索引 + 冲突重试。
- 版本：三段式 `V主.次.修订`；更新按 `major/minor/patch`（默认 patch）递增；`(file_id, version)` 唯一。
- 重名：同工序代码下未删除文件名称唯一；比较前归一化（去首尾空白、压缩连续空白、英文大小写不敏感），由 `process_files.name_key` 唯一索引兜底，软删除后名称可复用。

### 8.3 文件清单

- 每次刷新生成新快照（`catalog_snapshots`）与条目（`catalog_items`），条目下载链接按需生成。
- 触发：归档成功自动刷新（auto）、`POST /api/catalogs/refresh` 手动刷新（catalog_manage）、每日 `CATALOG_REFRESH_HOUR` 点自动刷新（auto，`ENABLE_SCHEDULER` 控制）。
- 同一秒内仅相同刷新方式 + 相同操作人的重复请求复用快照，manual 与 auto 不互相复用。
- 条目 `approved_at` 不落库，查询时由 `process_files.approved_at` 派生，缺失回退 `archived_at`。

---

## 9. API 概览

统一前缀 `/api`，认证头 `Authorization: Bearer <token>`；成功响应直接返回资源对象，错误结构 `{code, message, detail}`，分页结构 `{items, total, page, size, pages}`。

| 分组 | 路径 | 说明 |
| --- | --- | --- |
| 认证 | `POST /api/auth/login`、`POST /api/auth/register`、`GET /api/auth/me`、`POST /api/auth/change-password` | 登录、注册、当前用户、改密 |
| 用户/角色 | `GET/POST /api/users`、`GET/PUT/DELETE /api/users/{id}`、`PUT /api/users/{id}/roles`、`GET /api/roles`、`GET /api/permissions` | 用户管理（user_manage） |
| 文件 | `POST /api/files/upload`、`GET /api/files`、`GET/PUT/DELETE /api/files/{id}` | 上传、检索分页、详情、更新升版、软删除 |
| 版本/下载 | `GET /api/files/{id}/versions`、`GET /api/files/{id}/download?version=`、`GET /api/files/{id}/versions/{version}/download` | 版本历史与鉴权下载 |
| 审批动作 | `POST /api/files/{id}/submit-review`、`/review`、`/approve`、`/archive` | 状态机流转 |
| 审批查询 | `GET /api/files/{id}/approval`、`/signatures`、`/logs`、`GET /api/approvals/pending`、`GET /api/approvals/flows[/{id}]` | 流程、签名、待办 |
| 文件清单 | `GET /api/catalogs`、`POST /api/catalogs/refresh`、`GET /api/catalogs/snapshots[/{id}]` | 最新/历史快照查询 |
| 日志/统计 | `GET /api/logs`、`GET /api/stats/overview` | 操作日志（user_manage）、概览统计 |
| 系统 | `GET /`（302 → /ui/）、`GET /health`、`GET /docs` | 前端入口、健康检查、文档 |

字段、错误码、权限矩阵的完整定义以 [docs/API.md](docs/API.md) 为准。

---

## 10. 测试与自测

```bash
# 自动化测试（tests/ 由 qa 维护，使用临时 SQLite，不依赖 MySQL）
pip install -r requirements-dev.txt
python -m pytest -q

# 进程级冒烟（真实 HTTP）
python run.py                                   # 终端 1
curl http://127.0.0.1:8000/health               # 终端 2
# 登录→上传→提交→审核→批准→归档→清单→下载 全流程见 docs/API.md §12 curl 示例
```

---

## 11. 常见问题

| 现象 | 处理 |
| --- | --- |
| Windows 下启动报 ZoneInfoNotFoundError | 依赖已包含 tzdata；若手工环境缺失，`pip install tzdata` |
| 登录提示用户不存在 | `.env` 中未设置 `SEED_PASSWORD`，或未以 `ENV=dev` / `SEED_DEMO_USERS=true` 启动；设置后重启 |
| 上传返回 413 | 文件超过 `MAX_FILE_SIZE`（默认 50MB），可在 `.env` 调整 |
| 上传返回 429 | 同用户 2 秒内重复上传；调整 `UPLOAD_COOLDOWN_SECONDS` 或稍后重试 |
| 下载 401 | 下载接口需要 `Authorization` 头，前端须用 `fetch` + `blob` 而非 `<a href>` 直链 |
| 清单页为空 | 尚无已批准/已归档文件；归档后自动刷新，或调用 `POST /api/catalogs/refresh` |
| 想重置开发数据 | 停止服务，删除 `data/processms.db` 与 `uploads/` 后重启（会重新建表+种子） |
| MySQL 中文乱码 | 数据库/表使用 `utf8mb4`，连接串带 `?charset=utf8mb4` |

---

## 12. 开发约定

- 全链路异步：路由/依赖/CRUD 均 `async def` + `AsyncSession`，禁止在异步代码中混用同步 Session。
- 事务边界在路由层：一次请求一次 `commit`；CRUD 只 `flush`；审批/归档等多表写入在同一事务内。
- 配置只从环境变量/`.env` 读取，密钥与口令不写入代码与文档。
- 时间统一以 UTC naive 入库，接口输出 ISO8601 +00:00；业务日期（编号年月、快照号、日期筛选）按 `CATALOG_TZ` 解释。
- 错误码与错误结构、分页参数、状态枚举以 [docs/API.md](docs/API.md) 为唯一依据。
