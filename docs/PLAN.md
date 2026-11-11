# 工艺文件管理系统 项目实施计划（PLAN）

| 项 | 值 |
| --- | --- |
| 文档版本 | v1.0.3（接口冻结基线；变更见 §16） |
| 作者 | 项目经理（pm） |
| 评审 | Lead（原 chief 评审职责已并入） |
| 日期 | 2026-11-11 |
| 需求依据 | 工艺文件管理系统.md（只读，禁止修改） |
| 配套文档 | docs/API.md（REST 契约，唯一接口依据） |

---

## 0. 文档约定

1. 本计划是施工依据：范围、模型、状态机、编号/版本、RBAC、清单、安全、任务分解均以本文为准。
2. 接口字段、状态码、错误码、权限以 `docs/API.md` 为准；本文与其冲突时，接口细节以 API.md 为准，业务规则以本文为准。
3. 施工者只改自己 write scope 内文件；跨文件接口/字段变更必须先消息沟通，禁止"顺手改别人的文件"。
4. 禁止任何 git 写操作（commit/branch/push/checkout/tag）；git 由 Lead 统一处理。
5. 代码注释、API 提示、UI 文案全部中文；交付代码必须可运行、可测试，不留 TODO 占位。
6. 密钥、密码、数据库口令一律走环境变量，禁止写入代码与文档。

---

## 1. 项目目标与范围

### 1.1 目标

把当前"能 import、不能跑通"的半成品，修成**可运行、可测试、可演示**的工艺文件管理系统，覆盖需求文档的核心闭环：

编制（上传/更新）→ 组长审核 → 主管批准 → 签名留痕 → 资料员归档 → 自动/手动更新文件清单 → 按文件名/编号/编制人/工序检索 → 全流程审计。

验收基线：`python -m pytest` 全绿；`python run.py` 启动后可用 curl 完成"登录→上传→审核→批准→归档→清单→下载"全流程；`/ui` 页面可完成同样操作。

### 1.2 范围内（In Scope）

- P0 修复：异步全链路、lifespan 初始化、配置/依赖、状态枚举统一。
- RBAC：5 角色、9 权限、资源级校验（本人/审批人/管理员）。
- 文件：上传、列表、详情、搜索分页、更新（版本升级）、软删除、受控下载。
- 编号：工序代码-YYYYMM-4 位流水号，唯一且并发安全。
- 版本：Vx.y.z，major/minor/patch 规则，审核中锁定。
- 审批：提交审核、审核、批准、驳回、归档、流程与签名查询、待办。
- 文件清单：快照表 + 手动刷新 + 每日 0 点自动刷新 + 条目下载链接。
- 操作日志、统计概览、统一异常/错误码、统一分页。
- Web 管理界面（纯静态 HTML/CSS/JS，无构建链）。
- 自动化测试（pytest-asyncio + httpx ASGITransport + SQLite）与进程级冒烟。
- README、`.env.example`、Dockerfile、docker-compose（MySQL 保留）。

### 1.3 范围外（Out of Scope，明确不做，避免误解）

| 项 | 原因 |
| --- | --- |
| Office/PDF 转换 | 需求中仅"是否需要转换？"的疑问，非确定需求 |
| 邮件/短信/站内通知 | 文档未要求；驳回信息通过审批记录与待办体现 |
| 单用户登录/互踢、在线状态 | 文档中自问自答式疑问；JWT 无状态，明确不做 |
| 工序分工 | 需求"人员系统-分工"为疑问式条目、无字段定义；本轮不做，由 Lead 向用户确认（若实现需新增模型与任务） |
| 审批人失效自动改派 | 本轮不做；卡单处理方式=驳回后重新提交（见 §14 风险），改派接口列 P2 |
| 编制人/上传人分离（工序交接） | 上传人=编制人（creator=uploader），不支持指定他人为编制人；交接列 P2 |
| 分片上传、断点续传 | 50MB 内同步分块上传足够；前端做进度条与防重复提交 |
| 审批流程可视化配置 | 固定两级（审核→批准），流程数据仍落库，后续可扩展 |
| Alembic 数据库迁移 | 无生产存量数据；开发态 `create_all` + 种子脚本，生产 DDL 见 §5.4 |
| CSV/Excel 清单导出 | P2，视时间余量追加，不进入验收 |
| 多租户、消息中心、回收站 UI | P2 |

---

## 2. 现状问题清单

代码基线：1274 行，FastAPI + SQLAlchemy 2.0 + JWT，模型齐全但路由/CRUD 全是同步实现。

### 2.1 P0（阻断运行或安全，必须修）

| 编号 | 问题 | 定位 | 影响 | 修复方案 |
| --- | --- | --- | --- | --- |
| P0-01 | 数据库层异步、调用层同步：`database.py` 用 `AsyncSession`，而 `crud/user.py`、`crud/file.py`、`dependencies/auth.py`、`routers/*.py` 全部 `def` + `Session` | database.py:1-58；crud/user.py:1-57；crud/file.py:1-106；dependencies/auth.py:1-45；routers/auth.py:17、routers/users.py:10、routers/files.py:12 | 请求必现 500 或 coroutine 泄漏，系统不可用 | 全链路 `async def` + `AsyncSession` + `await`；删除同步 engine/session 与 `init_data.py` 的同步用法 |
| P0-02 | `init_db()` 在模块级调用但未 `await`，协程从未执行；建目录/建表/挂载都发生在 import 期 | main.py:22-27、main.py:55 | 表不存在，任何查询失败；reload 时重复副作用 | 改用 `lifespan`：启动时 `await init_db()`、建目录、启动调度器；关闭时 dispose |
| P0-03 | 依赖缺失且与实际代码不一致：缺 `aiosqlite/asyncmy/pydantic-settings/PyJWT/bcrypt/httpx/pytest`，却声明 `python-jose/passlib` | requirements.txt:1-9；utils/security.py:1-35 | 全新环境装完仍无法启动；jose 与 jwt 混用 | 重写 requirements.txt（含 MySQL 驱动与开发依赖分离），用 PyJWT + bcrypt 直连 |
| P0-04 | `config.py` 回退 `pydantic.BaseSettings`（v2 已移除）；`ALLOWED_ORIGINS` 定义了但 main.py 用 `["*"]`；SECRET_KEY 硬编码默认值 | config.py:3-33；main.py:44-52 | 新环境 `ImportError`；CORS 与配置失效 | Pydantic v2 `BaseSettings`；用 `get_settings()` 单例；CORS 读配置；无 SECRET_KEY 且生产环境直接拒绝启动 |
| P0-05 | 状态双枚举：`models/file.py` 为 `enum.Enum` 且列类型 `Enum(FileStatus)`；`schemas/file.py` 为 `str,Enum` | models/file.py:8-15、41；schemas/file.py:6-12；routers/files.py:161；crud/file.py:40 | 响应校验失败/写入值不一致（MySQL 存名、SQLite 存名，前端期望字符串） | 统一为 int：0 删除、1 草稿、2 待审核、3 待批准、4 已批准、5 已归档；模型 `SmallInteger`，schema `int + file_status_text` |
| P0-06 | `/uploads` 静态目录无鉴权挂载 | main.py:55 | 任意人可枚举/下载全部工艺文件（越权+路径可猜） | 移除静态挂载，改为 `GET /api/files/{id}/download` 鉴权下载（校验任务可见性） |
| P0-07 | RBAC 模型齐全但从未校验：所有接口只 `get_current_user` | routers/users.py:1-97（全部）、routers/files.py:1-183（全部） | 任意登录用户可建用户/删用户/审核/删除文件，权限系统形同虚设 | 新增 `dependencies/permissions.py：require_permission(code) + 资源级 owner/审批人校验；接口逐条标注权限 |
| P0-08 | 审批只实现"提交审核=置状态"，无 flow/steps 落库；审核、批准、驳回、归档、签名、待办、流程查询全部缺失 | routers/files.py:143-183；models/file.py:78-103 | 文件永远停在状态 2，无法闭环 | 接入 `approval_flows/approval_steps`；两级固定流程；新增 review/approve/archive/pending/flows 接口与签名表 |
| P0-09 | 编号规则错误且并发不安全：`工序前3字符-YYYYMMDDHHMMSS`；中文工序名取前 3 字符产生乱码；无唯一序列 | utils/file_upload.py:40-51；crud/file.py:10 | 编号不符合文档；并发上传触发唯一键冲突 500 | 新增 `file_number_sequences` 表，按 `(process_code, YYYYMM)` 自增，格式 `CODE-YYYYMM-NNNN`，冲突重试 |
| P0-10 | 版本更新固定 `minor`、无格式校验；审核中仍可上传新版本；版本记录可重复 | routers/files.py:106-140；utils/versioning.py:1-37 | 版本不可控，审批内容与文件不一致 | 校验 `^V\d+\.\d+\.\d+$`；请求指定 major/minor/patch（默认 patch）；状态 2/3 返回 409；`(file_id, version)` 唯一 |
| P0-11 | 搜索字段未实现：`creator_name/upload_date_start/upload_date_end` 声明但 crud 忽略；列表无 total | schemas/file.py:66-73；crud/file.py:55-74 | 文档核心检索需求（编制人/日期）缺失，前端无法分页 | 实现多条件检索（含 join users 按编制人姓名）+ 统一分页结构 |
| P0-12 | 文件清单功能完全缺失 | 全仓库无 catalog 相关模型/路由/调度 | 文档核心需求缺失 | 新增 `catalog_snapshots` + `catalog_items`；归档自动刷新 + 手动刷新 + 每日 0 点调度 |
| P0-13 | 软删除未落地：无文件删除接口；用户删除仅 `is_active=False` 且无权限校验 | routers/files.py（无 delete）；routers/users.py:72-97 | 无法下架文件；可删任意用户含管理员 | 文件状态 0 + `deleted_at/deleted_by`；列表/详情/下载一律过滤；自删/删最后一个 admin 拒绝 |
| P0-14 | 事务边界散乱：CRUD 内各自 `commit`；审批多表写入无原子性；日志与业务写分离 | crud/user.py:33-35、50-52；crud/file.py:32-34、57-60、81-92、103-105 | 流程半写、日志丢失，数据不一致 | 路由层持有事务边界（`async with db.begin()` 或统一 `commit` 一次）；CRUD 只 `flush` |
| P0-15 | 路由导入异常被 `try/except ImportError` 吞掉；模块级副作用让 `reload=True` 双初始化 | main.py:57-69；run.py:10-16 | 路由缺失仍返回 200 健康，问题被掩盖；开发期抽风 | 直接 import，失败即启动失败；lifespan 承担初始化；`run.py` 关闭 reload |
| P0-16 | Pydantic v1 API 残留 `.dict()`；`datetime.utcnow()` 到处用；IP 硬编码 `127.0.0.1` | routers/files.py:127；crud/*.py；routers/files.py:48、138 | 未来 pydantic 报错；审计日志失真 | 统一 `model_dump`；`datetime.now(timezone.utc)` 存入、响应 ISO8601；IP 从 `Request.client` 取 |
| P0-17 | 无种子数据：`init_data.py` 只建 admin/test 两个无角色用户，且用同步 Session；roles/permissions 表永远是空的 | init_data.py:1-52 | RBAC 无从谈起，演示无审批人 | 重写为异步种子脚本：9 权限、5 角色、角色权限矩阵、5 演示账号（密码走环境变量，默认仅开发） |
| P0-18 | 无 `.env.example`/README 说明/Dockerfile；模块级建库建目录 | 仓库根目录；main.py:22-27 | 新人无法启动；无法演示部署 | 补齐；README 含 SQLite 一键启动与 MySQL 切换说明 |

### 2.2 P1（影响体验/可维护性，本轮尽量做）

| 编号 | 问题 | 修复方案 |
| --- | --- | --- |
| P1-01 | 上传一次性读入内存、无进度、无防重复提交 | 分块读取（1MB）边写边算大小与 sha256；上传接口按用户 2 秒冷却返回 429 |
| P1-02 | 操作日志无筛选分页、无 IP/UA、无目标类型 | `GET /api/logs` 分页筛选；日志表加 `target_type/target_id/ip/user_agent` |
| P1-03 | 无统计概览 | `GET /api/stats/overview`（文件状态分布、我的待办、清单最近刷新、最近操作） |
| P1-04 | 无前端 | web/ 纯静态页面（登录、文件、审批、清单、用户、日志、概览） |
| P1-05 | 时间/时区混乱 | 统一 UTC 存储，响应 `+00:00` ISO8601；清单调度按 `Asia/Shanghai` 计算 0 点，可用 `CATALOG_TZ` 覆盖 |
| P1-06 | CORS 不环境化 | `ALLOWED_ORIGINS` 逗号分隔环境变量；生产禁止 `*` + credentials |
| P1-07 | 无统一异常处理/错误码/422 结构 | `utils/exceptions.py` + 全局 handler：`{code,message,detail}` |
| P1-08 | 无测试、无 CI 冒烟 | tests/ 11 个用例文件 + `pytest.ini` + 进程级冒烟脚本 |

### 2.3 P2（记录，不承诺）

Alembic 迁移；清单 CSV 导出；清单版本差异对比；审批流程自定义；通知；文件在线预览；回收站 UI；操作日志导出；密码强度策略加强（zxcvbn）；多因素认证。

---

## 3. 架构决策（ADR 摘要）

| 编号 | 决策 | 理由 | 落点 |
| --- | --- | --- | --- |
| D1 | **异步全链路**：路由/依赖/CRUD 全 `async def`，用 `AsyncSession`，无同步 Session | 现有 database.py 已选异步引擎，改为同步成本更高；统一避免混用崩溃 | config.py、database.py、crud/*、dependencies/*、routers/* |
| D2 | 保持**扁平分层**（不引入 services 包之外的框架）：routers → crud → models；跨表业务放 `services/` | 团队规模小；沿用现有目录减少冲突；审批/清单有多表逻辑，需独立服务层 | 新增 `services/approval_service.py`、`services/catalog_service.py`、`services/scheduler.py` |
| D3 | **统一异常与错误码**：业务异常继承 `AppError`"（HTTP 状态 + 字符串错误码 + 中文 message），全局 handler 输出 `{code,message,detail}`；422 也归一化 | 前端只认 code；避免英文默认错误 | utils/exceptions.py、main.py |
| D4 | **配置**：pydantic-settings v2，`.env` + 环境变量；`ENV=dev/prod`；dev 默认 SQLite，prod 必须显式 MySQL 与 SECRET_KEY | 满足"SQLite 跑通、MySQL 保留"；密钥不落库 | config.py、.env.example |
| D5 | **数据库**：`DATABASE_URL` 单入口，dev `sqlite+aiosqlite:///./data/processms.db`，prod `mysql+aiomysql://user:pass@host/db?charset=utf8mb4`（asyncmy 可选但当前依赖为 aiomysql）；启动 `create_all` + 种子幂等 | 免迁移负担；演示可零依赖 | database.py、init_data.py |
| D6 | **文件存储**：`UPLOAD_DIR/{yyyy}/{mm}/{uuid4}.{ext}`，DB 存相对路径；下载只走受控接口，绝不用 `StaticFiles` 暴露上传目录 | 防目录穿越与越权枚举；便于迁对象存储 | utils/file_upload.py、routers/files.py |
| D7 | **鉴权**：JWT（PyJWT，HS256，`sub=username`、`uid`、`exp`）；每请求查库加载角色/权限（不把权限塞 token） | 权限变更立即生效；token 不带敏感角色数据 | utils/security.py、dependencies/auth.py |
| D8 | **事务**：权限校验后，路由层一次 `commit`；审批/归档/清单多表写入在 service 内单事务；日志同事务写 | 保证状态机与审计原子 | crud/*.py、services/*.py |
| D9 | **时间**：DB 统一存 UTC naive；响应补 `+00:00` 的 ISO8601；日期型查询按业务时区 `CATALOG_TZ`（默认 Asia/Shanghai）换算为 UTC 区间；前端按本地时区展示 | 避免 naive/aware 比较异常与 8 小时偏差 | utils/time.py、schemas |
| D10 | **编号/版本生成器**：纯函数放 `utils/file_number.py` / `utils/versioning.py`，发号在 `crud/file.py` 内用序列表完成 | 可单测；并发控制在唯一处 | utils/*、crud/file.py |
| D11 | **每日 0 点刷新**：`asyncio` 后台任务（lifespan 启动/关闭取消），单 worker 运行；`ENABLE_SCHEDULER` 开关；多 worker 时只允许一个实例（文档说明） | 不引入 APScheduler/Celery 重依赖 | services/scheduler.py |
| D12 | **前端**：纯静态 `login.html` + 单页 `app.html`（tab 切换，不用 iframe），共享 `api.js`（token/401/错误处理），`fetch` 调 `/api`，token 存 `sessionStorage`，上传用 XHR 取进度；后端 `/ui` 挂载 + `/` 302 到 `/ui/` | 无 npm 构建链；单页避免登录态/错误处理重复实现 | web/、main.py |
| D13 | **测试**：pytest-asyncio(auto) + httpx `ASGITransport` + 临时 SQLite 文件库，每用例独立事务/重建；依赖覆盖 `get_db` 与 `get_current_user` 的库内真实数据 | 快、无外部依赖、能测真实路由与权限 | tests/、pytest.ini |

---

## 4. 目标目录结构

```
ProcessMS/
├── config.py                  # Settings（pydantic-settings v2）+ get_settings()
├── database.py                # async engine / AsyncSessionLocal / Base / get_db / init_db / close_db
├── main.py                    # lifespan、异常 handler、CORS、路由注册、/ui 挂载、/health
├── run.py                     # 本地启动入口（uvicorn，无 reload）
├── init_data.py               # 异步种子：权限/角色/演示账号（幂等）
├── requirements.txt           # 运行依赖
├── requirements-dev.txt       # pytest 等开发依赖
├── pytest.ini
├── .env.example
├── README.md
├── Dockerfile
├── docker-compose.yml         # app + mysql8
├── docs/
│   ├── PLAN.md                # 本文
│   ├── API.md                 # 接口契约
│   └── REVIEW.md              # 评审记录（Lead）
├── models/
│   ├── __init__.py            # 显式导出全部模型，保证 Base.metadata 完整
│   ├── user.py                # User/Role/Permission/UserRole/RolePermission
│   ├── file.py                # ProcessFile/FileVersion/FileOperationLog/FileStatus 常量
│   ├── approval.py            # ApprovalFlow/ApprovalStep/FileSignature
│   └── catalog.py             # CatalogSnapshot/CatalogItem/FileNumberSequence
├── schemas/
│   ├── common.py              # Page/PagedResponse/ErrorResponse/MessageResponse
│   ├── auth.py
│   ├── user.py
│   ├── file.py
│   ├── approval.py
│   ├── catalog.py
│   ├── log.py
│   └── stats.py
├── crud/
│   ├── __init__.py
│   ├── user.py                # 用户/角色/权限查询
│   ├── file.py                # 文件/版本/编号序列/日志
│   ├── approval.py
│   ├── catalog.py
│   └── stats.py
├── services/
│   ├── __init__.py
│   ├── approval_service.py    # 状态机：提交/审核/批准/驳回/归档/签名
│   ├── catalog_service.py     # 快照生成/查询
│   └── scheduler.py           # 每日 0 点刷新任务
├── routers/
│   ├── auth.py / users.py / roles.py / files.py / approvals.py / catalogs.py / logs.py / stats.py
├── dependencies/
│   ├── auth.py                # get_current_user / get_current_active_user
│   └── permissions.py         # require_permission / 资源级校验辅助
├── utils/
│   ├── security.py            # bcrypt + PyJWT
│   ├── file_number.py         # 工序代码规整 + 编号拼接
│   ├── versioning.py          # 版本解析/递增/校验
│   ├── file_upload.py         # 上传校验/分块落盘/安全路径解析
│   ├── exceptions.py          # AppError + 错误码常量
│   ├── pagination.py          # 分页参数解析
│   └── logging_utils.py       # 操作日志写入（同事务）
├── web/                       # 纯静态管理界面（frontend 负责）
├── tests/                     # pytest（qa 负责）
├── uploads/                   # 运行时生成（gitignore）
├── data/                      # SQLite 文件（gitignore）
└── logs/                      # 运行日志（gitignore）
```

> 注：`web/`、`tests/`、`docs/REVIEW.md` 分别由 frontend、qa、Lead 负责，backend 只负责挂载与 README 指引。

---

## 5. 数据模型变更

### 5.1 表总览

| 表 | 状态 | 说明 |
| --- | --- | --- |
| users | 保留，微调 | 加 `updated_at`；密码字段 `password_hash`；`is_active` 软禁用 |
| roles | 保留 | 种子 5 角色 |
| permissions | 保留 | 种子 9 权限码 |
| user_roles / role_permissions | 保留 | 种子矩阵；唯一约束 `(user_id,role_id)`、`(role_id,permission_id)` |
| process_files | **调整** | 状态改 int；加 `process_code/deleted_at/deleted_by/archived_at/archived_by`；去掉无用 `approval_flow` 文本列；补索引 |
| file_versions | 保留，微调 | 加 `file_hash`；唯一 `(file_id, version)`；`version` 索引 |
| file_operation_logs | **调整** | `file_id` 可空；加 `target_type/target_id/user_agent`；补组合索引 |
| approval_flows | 保留，微调 | 加 `version`（审批针对的版本）、`reject_reason`；状态 0 终止/1 进行中/2 已完成 |
| approval_steps | 保留，微调 | 唯一 `(flow_id, step_number)`；`approval_status` 0/1/2；`approver_id` 必填 |
| file_signatures | **新增** | 审核/批准签名留痕 |
| catalog_snapshots | **新增** | 文件清单刷新批次 |
| catalog_items | **新增** | 清单快照条目（快照 + 条目两步存储） |
| file_number_sequences | **新增** | 编号流水号，保证唯一 |

### 5.2 字段明细

#### process_files
| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | Integer | PK | |
| file_number | String(32) | unique, index, not null | 编号，生成后不可变 |
| file_name | String(255) | not null | 文件名称（原值展示） |
| name_key | String(320) | unique, null | 重名归一化键：`process_code + ':' + normalize(file_name)`；软删置 NULL 以允许复用 |
| file_type | String(20) | | 扩展名（.pdf 等） |
| process_code | String(8) | not null, index | 工序代码（2-4 位大写字母数字） |
| process_step | String(100) | not null, index | 工序名称 |
| version | String(20) | not null | 当前版本 Vx.y.z |
| uploader_id | Integer FK users.id | not null | 上传人 |
| creator_id | Integer FK users.id | not null, index | 编制人 |
| initial_upload_time | DateTime | not null, index | 首次上传 |
| last_update_time | DateTime | not null, index | 最后更新 |
| file_size | BigInteger | | 字节 |
| storage_path | String(500) | not null | 相对路径，不对外暴露 |
| file_status | SmallInteger | not null, default 1, index | 0-5，见 §6.1 |
| current_approver_id | Integer FK users.id | null | 当前待办审批人 |
| approved_at | DateTime | null | 批准通过时间（批准环节写入；清单条目 `approved_at` 的派生源） |
| archived_at / archived_by | DateTime / Integer | null | 归档信息 |
| deleted_at / deleted_by | DateTime / Integer | null | 软删除信息 |
| remarks | Text | | 备注 |

#### file_versions
id、file_id(FK, index)、version(String(20))、file_path(String(500))、file_hash(String(64))、uploader_id(FK)、upload_time(DateTime)、change_description(Text)、file_size(BigInteger)；唯一 `(file_id, version)`。

#### approval_flows
id、file_id(FK, index)、version(String(20))、flow_type(String(20)="standard")、current_step(Integer default 1)、status(Integer default 1，0 终止/1 进行中/2 已完成)、initiator_id(FK)、created_at、completed_at、reject_reason(Text)；索引 `(file_id, status)`。

#### approval_steps
id、flow_id(FK, index)、step_number(Integer)、step_name(String(100))（"组长审核"/"主管批准"）、approver_id(FK, index)、approval_status(Integer default 0)、approval_time(DateTime)、approval_comment(Text)；唯一 `(flow_id, step_number)`。

#### file_signatures
id、file_id(FK, index)、version(String(20))、step_type(String(20))（review/approve）、step_name(String(100))、signer_id(FK)、signer_name(String(50))（冗余快照）、signed_at(DateTime)、remark(Text)；索引 `(file_id, signed_at)`。签名文案由后端生成：`{姓名}（{角色}）于 {yyyy-MM-dd HH:mm} 审批通过`。

#### catalog_snapshots
id、snapshot_no(String(32), unique)（`QD-YYYYMMDDHHMMSS`）、refresh_type(String(10))（manual/auto）、operator_id(FK, null=自动)、item_count(Integer)、created_at(DateTime, index)。

#### catalog_items
id、snapshot_id(FK, index)、file_id(FK)、file_number(String(32))、file_name(String(255))、version(String(20))、process_code、process_step、creator_id、creator_name(String(50))、file_size(BigInteger)、file_status(Integer)；**不存 approved_at**，接口返回时由 `process_files.approved_at` 派生（缺失回退 `archived_at`）；唯一 `(snapshot_id, file_number)`；下载链接不落库，由接口按 `/api/files/{file_id}/download?version={version}` 生成。

#### file_number_sequences
id、process_code(String(8))、period(String(6))（YYYYMM）、last_seq(Integer default 0)、updated_at(DateTime)；唯一 `(process_code, period)`。

### 5.3 索引清单（SQLAlchemy 层声明）

- process_files：`uq(file_number)`；`uq(name_key)`（重名归一化键）；`ix(process_code, initial_upload_time)`；`ix(file_status, last_update_time)`；`ix(creator_id)`；`ix(file_name)`；`ix(process_step)`。
- file_versions：`uq(file_id, version)`。
- file_operation_logs：`ix(file_id, operation_time)`、`ix(operator_id, operation_time)`、`ix(operation_type)`。
- approval_flows：`ix(file_id, status)`。
- approval_steps：`uq(flow_id, step_number)`、`ix(approver_id, approval_status)`（待办查询）。
- catalog_items：`uq(snapshot_id, file_number)`（快照内编号唯一）。
- file_number_sequences：`uq(process_code, period)`。

### 5.4 初始化与生产变更策略

1. 开发/测试：删除 `data/processms.db` 后启动即 `create_all`，再执行 `python init_data.py` 幂等种子。
2. MySQL 生产：首次部署同样 `create_all`；后续字段变更在 `docs` 记录 DDL，待引入 Alembic（P2）后接管。**本轮不允许** 在代码里写"自动 ALTER"。
3. 种子幂等：按 `code/name` 查询后 `insert if absent`；角色权限矩阵每次种子都校正（删除多余关联）。
4. 演示账号种子策略（Lead 决策）：**仅当** `ENV=dev` 或显式 `SEED_DEMO_USERS=1` 时创建演示账号 admin/engineer01/leader01/manager01/archivist01；演示账号口令**必须**来自环境变量 `SEED_PASSWORD`（未提供则拒绝创建并输出中文提示），不得硬编码进业务逻辑/种子代码；**任何文档、README、.env.example 只出现变量名与占位符（如 `<SEED_PASSWORD>`），不得出现真实口令值**。
5. 配置说明：`.env.example` 与 README 必须列出 `ENV`、`DATABASE_URL`、`SECRET_KEY`、`ALLOW_REGISTER`、`SEED_DEMO_USERS`、`SEED_PASSWORD`、`ENABLE_SCHEDULER`、`CATALOG_TZ`、`ALLOWED_ORIGINS`、`UPLOAD_DIR`、`MAX_FILE_SIZE`、`ACCESS_TOKEN_EXPIRE_MINUTES` 的含义与默认值；密钥类变量只给占位符，不含真实值。
6. 环境相关默认值：`ALLOW_REGISTER` 代码默认 false（`.env.example` 的开发配置写 true）；prod 未显式配置时强制 false；`SEED_DEMO_USERS` 默认 false（dev 的 `.env.example` 写 true，启用时必须提供 `SEED_PASSWORD`）；prod 缺 `SECRET_KEY` 拒绝启动。

---

## 6. 审批状态机

### 6.1 文件状态码（int，全系统唯一口径）

| 值 | 常量 | 中文 | 说明 |
| --- | --- | --- | --- |
| 0 | DELETED | 已删除 | 软删除，所有列表/详情/下载过滤 |
| 1 | DRAFT | 草稿 | 新建/驳回后的可编辑态 |
| 2 | PENDING_REVIEW | 待审核 | 组长审核中 |
| 3 | PENDING_APPROVAL | 待批准 | 主管批准中 |
| 4 | APPROVED | 已批准 | 待归档 |
| 5 | ARCHIVED | 已归档 | 进入文件清单 |

审批流状态：0 已终止（驳回）、1 进行中、2 已完成。步骤状态：0 待处理、1 通过、2 驳回。

### 6.2 迁移表

| # | 动作 | 前置状态 | 目标状态 | 操作人/权限 | 副作用（同事务） |
| --- | --- | --- | --- | --- | --- |
| 1 | 上传 | — | 1 DRAFT | upload；本人 uploader=creator | 生成编号；计算 name_key（重名唯一）；写 file_versions V1.0.0；日志 upload |
| 2 | 提交审核 submit-review | 1 | 2 | update+本人，或 admin | 创建 flow(status=1,current_step=1) + step1(组长审核,approver=指定/自动)；**step2 在审核通过时创建**；提交说明写 operation_details；日志 submit_review |
| 3 | 审核通过 review(pass) | 2 | 3 | review + 必须为 step1 approver | step1=1、step1.approval_time；flow.current_step=2；写审核签名；current_approver_id=主管；日志 review_pass |
| 4 | 审核驳回 review(reject) | 2 | 1 | review + step1 approver | step1=2；flow.status=0、completed_at；file 回草稿；写驳回签名（签名 step_type=review）；日志 review_reject |
| 5 | 批准通过 approve(pass) | 3 | 4 | approve + 必须为 step2 approver | step2=1；flow.status=2、completed_at；file.approved_at=now；写批准签名；日志 approve_pass |
| 6 | 批准驳回 approve(reject) | 3 | 1 | approve + step2 approver | step2=2；flow.status=0；file 回草稿；写驳回签名；日志 approve_reject |
| 7 | 归档 archive | 4 | 5 | archive | archived_at/by；自动刷新清单快照；日志 archive |
| 8 | 更新 update | 1 | 1 | update + 本人/admin | 版本递增（major/minor/patch 默认 patch）；写新版本记录；last_update_time；日志 update |
| 9 | 更新（已批准/已归档） | 4/5 | 1 | update + 本人/admin | 版本递增（默认 patch）→ 回到草稿并需重新审批；日志 update |
| 10 | 软删除 delete | 1/4/5 | 0 | delete + （本人草稿）或 admin；2/3 禁止 | deleted_at/by；清单不刷新（下次刷新自然剔除）；日志 delete |
| 11 | 重新提交 | 1 | 2 | 同 #2 | 每次提交新建一条 flow（历史流程保留，可追溯） |

**并发与幂等（P0，必须实现）**：

- 审核/批准的状态迁移使用**条件更新**：`UPDATE approval_steps SET approval_status=?, approval_time=?, approval_comment=? WHERE id=? AND approval_status=0`；`rowcount=0` → 409 `APPROVAL_ALREADY_DONE`，禁止"先写签名/日志后校验"。
- 步骤、签名、文件状态、flow 状态、操作日志在**同一事务**提交，任一步失败整体回滚。
- `step2` 在审核通过时创建（不在提交时创建）；并发/重复请求由条件更新天然幂等。
- 归档 + 清单快照刷新、提交审核 + flow/steps 创建同样要求单事务原子性；并发手动刷新返回 409 `REFRESH_IN_PROGRESS`。
- 验收：同一审批人并发/连续提交两次仅一次生效（qa 必测）。

### 6.3 非法操作统一响应

- 状态不匹配：`409 STATE_CONFLICT`，message 例："当前状态为待审核，不可执行批准"。
- 审核中更新/删除：`409 FILE_LOCKED`，"审核中的文件禁止更新/删除"。
- 非当前步骤审批人：`403 FORBIDDEN`，"您不是该步骤的审批人"。
- 流程已完成/已终止仍操作：`409 STATE_CONFLICT`。
- 同一文件重复提交审核：`409 STATE_CONFLICT`。
- 归档非已批准文件：`409 STATE_CONFLICT`。

### 6.4 审批人与签名细节

- 提交时请求可指定 `reviewer_id`（须有 review 权限）与 `approver_id`（须有 approve 权限）；未指定则按"最早创建的活跃用户中具备对应权限者"自动分配，找不到则 `409 NO_ELIGIBLE_APPROVER`（种子数据必须保证存在）。
- step2 在审核通过时创建（assign 主管），避免未审核就被批准；审核通过时若预分配主管已被禁用/不存在，回退自动分配“最早创建的具备 approve 权限的活跃用户”，仍无则 `409 NO_ELIGIBLE_APPROVER`（审批人失效最小兜底，改派接口列 P2）。
- 意见/说明落库口径：审核/批准意见同时写 `approval_steps.approval_comment` 与 `file_signatures.remark`；**提交审核说明**与**归档说明**不单独建列，写入 `file_operation_logs.operation_details`（operation_type 分别为 `submit_review`/`archive`）。
- 签名 **统一在流程节点自动添加**（不额外做"签名管理"接口）：审核/批准通过或驳回时写 `file_signatures`；批准通过即形成完整签名链（审核签名 + 批准签名）。
- 查询：`GET /api/files/{file_id}/approval`（当前/全部流程+步骤+签名）；`GET /api/files/{file_id}/signatures`；`GET /api/approvals/pending`（我的待办）。
- 可见性：待办只返回分配给当前用户的待处理步骤；流程明细对文件可见者、相关审批人、admin 可见。

### 6.5 软删除规则

- 文件：状态置 0 并保留行；列表/详情/下载/统计/清单全部过滤；编号不复用（唯一键仍占位，保证编号不可重用）。
- 恢复（P2，不做）；如需恢复由管理员直接改库或后续接口。
- 用户：`DELETE /api/users/{id}` 仅禁用（`is_active=False`），不允许删除自己、不允许禁用最后一个 admin。
- 审计日志不随软删消失。

---

## 7. RBAC 权限设计

### 7.1 权限码（9 个，落 permissions 表）

| 权限码 | 名称 | 语义 |
| --- | --- | --- |
| upload | 上传 | 新建工艺文件 |
| update | 更新 | 修改文件元数据/上传新版本 |
| delete | 删除 | 软删除文件（资源级限制见 7.3） |
| review | 审核 | 审核环节通过/驳回 |
| approve | 批准 | 批准环节通过/驳回 |
| reject | 驳回 | 驳回动作权限：审核/批准接口在 `result=reject` 分支校验该权限（通过分支不校验，通过分支要求 review/approve）；仍须为当前步骤审批人 |
| archive | 归档 | 已批准文件归档 |
| catalog_manage | 清单管理 | 手动刷新清单 |
| user_manage | 用户管理 | 用户/角色/权限管理、查看全量操作日志 |

### 7.2 角色-权限矩阵（种子数据必须与此一致）

| 角色 code | 中文 | upload | update | delete | review | approve | reject | archive | catalog_manage | user_manage |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| admin | 系统管理员 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| engineer | 工艺员（编制） | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| leader | 组长（审核） | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ |
| manager | 主管（批准） | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| archivist | 资料员（归档/清单） | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |

说明：
- admin 兜底拥有全部权限（即使关联缺失，权限检查对 admin 短路放行）。
- engineer 的 delete 仅限**本人创建的草稿/驳回态**文件（资源级校验见 7.3）。
- 一个用户可多角色，权限取并集。
- 无角色用户默认无任何业务权限，仅能 `GET /api/auth/me`、`POST /api/auth/change-password`。

### 7.3 资源级校验（权限之外的二层校验）

| 场景 | 规则 |
| --- | --- |
| 提交审核/更新/删除 | 需 owner（uploader_id 或 creator_id）或 admin；delete 额外限制：非本人只能 admin，且状态 2/3 一律禁止 |
| 审核 | 必须是当前 flow 中 `step_number=1 且 approver_id=当前用户` 且 `approval_status=0` |
| 审核/批准-驳回 | 除入口审批人校验外，`result=reject` 分支额外要求 `reject` 权限；通过分支不要求 reject（通过要求 review/approve） |
| 批准 | 必须是 `step_number=2` 的 approver |
| 归档 | 有 archive 权限即可（资料员/管理员） |
| 下载/详情 | 文件可见性规则（§10.3）；下载额外要求非删除态 |
| 用户管理 | 有 user_manage；操作对象不能是自己禁用自己、不能禁用最后一个 admin |
| 流程/签名/日志查询 | 文件可见者 + 相关审批人 + admin；全量日志仅 user_manage |

### 7.4 实现方式

- `dependencies/auth.py::get_current_user`：解 JWT → 查库 → 校验 `is_active` → 返回带 `id/username/roles/permissions` 的 `CurrentUser` 对象。
- `dependencies/permissions.py::require_permission(*codes)`：工厂函数依赖，缺权限抛 `403 FORBIDDEN_PERMISSION`（detail 带缺失权限码）。
- 资源级校验写在 `services/` 或路由内辅助函数，不散落魔法判断。
- 权限每请求查库（数据量小），不做缓存，保证变更立即生效。

---

## 8. 文件编号与版本规则

### 8.1 工序代码 process_code

- 格式：`^[A-Z0-9]{2,4}$`（大写字母/数字），上传与更新可填；不填默认 `GEN`。
- 建议字典（前端下拉，非强制）：CN 车削、MI 铣削、MO 磨削、WE 焊接、AS 装配、HT 热处理、QC 检验、PK 包装、GEN 通用。后端不做枚举硬校验，保证可扩展。
- 工序名称 process_step 为自由文本（1-100 字）。

### 8.2 编号规则

- 格式：`{process_code}-{YYYYMM}-{NNNN}`，如 `CN-202611-0001`。
- YYYYMM 取**首次上传时刻**（Asia/Shanghai 业务时区的年月）。
- NNNN 为该 `(process_code, YYYYMM)` 下自增流水号，从 0001 起，4 位，超过 9999 顺延为 5 位（不截断）。
- 唯一性：DB `unique(file_number)`；并发控制：`file_number_sequences` 行级自增，捕获 `IntegrityError` 重试（最多 5 次）。
  - MySQL：`SELECT ... FOR UPDATE` 锁序列行后 `UPDATE`。
  - SQLite：写锁串行 + 重试；测试需覆盖"并发 10 次上传编号唯一"。
- 编号生成后不可修改；文件软删除后编号不复用。

### 8.3 版本规则

- 格式：`^V\d+\.\d+\.\d+$`（V 大写；三段非负整数，无前导零）。
- 初始上传：请求可指定 `version`，默认 `V1.0.0`；指定值必须合法且未存在。
- 更新：`version_type` ∈ {major, minor, patch}，默认 patch；规则：
  - major → V(x+1).0.0；minor → Vx.(y+1).0；patch → Vx.y.(z+1)。
- 版本记录唯一 `(file_id, version)`；`change_description` 建议必填（更新时为空则写"未填写"）。
- 审核中（状态 2/3）**禁止**更新、禁止新增版本 → 409 FILE_LOCKED。
- 已批准/已归档文件更新：自动升版并回到草稿，需重新走完整审批；归档状态随之失效（保留 archived 历史字段，但状态以 1 为准重新流转）。
- 下载：默认下载 `process_files.version` 对应记录；指定 `?version=` 下载历史版本；文件缺失（磁盘被删）→ 404 FILE_CONTENT_MISSING。

### 8.4 文件重名规则（P0，v1.0.2 定稿）

- **决策**：需求原表"文件名称唯一"无法落地为全库唯一（不同工序复用通用文件名极常见，全库唯一将阻塞正常业务），收窄为**同一 `process_code` 下、未删除文件的文件名称唯一**；不同工序代码允许同名。
- **归一化**：`name_key = process_code + ':' + normalize(file_name)`；`normalize` = 去首尾空白 + 连续空白压缩为单空格 + 英文大小写折叠（Python `casefold()`）；中文不受影响；`file_name` 原值原样保存用于展示。
- **生效范围**：上传、改名（`PUT /api/files/{id}` 的 `file_name`）、升版时改名均需校验并维护 `name_key`；`process_files.name_key` 建唯一索引。
- **软删除复用**：软删除时把 `name_key` 置 NULL（保留历史行），因此删除后同名可再次上传；恢复（P2）时须重新做唯一性校验。
- **并发兜底**：应用层先查重（返回友好 409），最终由唯一索引兜底；捕获 `IntegrityError` 转 409 `FILE_NAME_DUPLICATED`。
- **SQLite/MySQL 差异**：两者唯一索引均允许多个 NULL（软删行不冲突）；SQLite 字符串比较大小写敏感，MySQL 默认 collation 常为大小写不敏感——因此**统一以 Python 归一化后的 `name_key` 判重**，不依赖数据库 collation；唯一索引只做并发兜底。
- **错误**：重名统一 409 `FILE_NAME_DUPLICATED`，message="同一工序代码下已存在同名文件"。
- **验收**：同名/仅大小写或空白差异 → 409；软删后同名 → 201；改名冲突 → 409；并发同名两次上传仅一个成功（qa 必测）。

### 8.5 示例

```
CN-202611-0001  V1.0.0   草稿 → 提交 → 审核通过 → 批准通过 → 归档
CN-202611-0001  V2.0.0   归档后大改：major 升版 → 回到草稿重新审批
CN-202611-0002  V1.0.1   patch 修订（换页/错别字）
```

---

## 9. 文件清单设计

### 9.1 设计选择

需求"文件清单进行分步存储，做为链接可打开；自动的同时增加手动按钮"。采用**快照式清单**：

- 每次刷新生成一个 `catalog_snapshots` 批次 + 若干 `catalog_items` 条目（两步存储，历史可追溯，避免实时 join 漂移）。
- 清单内容 = 当前所有 `file_status IN (4,5)` 且未删除的文件，取 `process_files` 当前版本。
- 条目字段见 §5.2；`download_url` 由接口按需生成，不落库，保证文件迁移后链接仍有效。
- 清单编号若需对外展示，使用 `catalog_items.file_number`（即工艺文件编号，天然唯一）；快照内以 `(snapshot_id, file_number)` 去重。

### 9.2 刷新触发

| 方式 | 触发 | 操作人 | 说明 |
| --- | --- | --- | --- |
| 自动（归档） | `POST /api/files/{id}/archive` 成功后 | 系统 | 归档即刷新，满足"确认后制作清单" |
| 自动（每日） | 每天 00:00（`CATALOG_TZ`，默认 Asia/Shanghai） | 系统 | `services/scheduler.py` 后台任务，失败记录日志并在下次触发重试 |
| 手动 | `POST /api/catalogs/refresh` | catalog_manage（archivist/admin） | 前端"刷新清单"按钮，返回新快照 meta |

幂等：每次刷新都新建快照（不做"无变化跳过"），保证"更新日期/更新方式"可查；同一秒内重复刷新用 `snapshot_no` 加随机后缀/序号避免唯一冲突，或先查同秒存在则复用（实现取后者：复用同秒快照）。

### 9.3 调度器实现要点

- lifespan 启动时若 `ENABLE_SCHEDULER=true`（默认 dev true、prod 按部署说明单实例）创建 `asyncio.create_task`。
- 循环：计算下一个 `CATALOG_TZ` 的 00:00:00 → `await asyncio.sleep(seconds)` → 调用 `catalog_service.refresh(refresh_type="auto", operator_id=None)` → 异常捕获记录 logger.exception 不终止循环。
- 关闭：`task.cancel()` + `suppress(CancelledError)`。
- 仅单 worker 部署启用；多 worker 时由部署方设置 `ENABLE_SCHEDULER=false` 并另起定时任务（README 说明）。
- 测试不启动真实定时器；调度函数 `next_run_at(now, tz)` 做纯函数单测。

### 9.4 查询与下载

- `GET /api/catalogs`：默认最新快照；参数 `snapshot_id` 可查历史；`keyword/process_step` 过滤条目；统一分页。
- 条目 `download_url = /api/files/{file_id}/download?version={version}`，点击后走鉴权下载并记 `download` 日志。
- 响应含 `snapshot` meta（编号/刷新方式/时间/条目数），前端展示"更新时间、更新方式"。
- `GET /api/catalogs/snapshots`：历史批次分页。

### 9.5 保留策略

快照永久保留（数据量小）；如需清理后续再加。清单查询默认只读最新，避免误用历史。

---

## 10. 搜索与分页规范

### 10.1 通用分页

- 请求：`page`（默认 1，≥1）、`size`（默认 10，1-100，超界 422 或钳制到边界——统一**钳制**并在响应回显实际值）。
- 响应：`{items: [...], total: int, page: int, size: int, pages: int}`，`pages = ceil(total/size)`（total=0 时 0）。
- 默认值：所有分页接口（文件/用户/日志/清单/快照/流程/待办）统一默认 `page=1, size=10`、最大 100（清单同样 10）；前端以响应回显的 `size` 渲染。
- 排序：`sort` 白名单 `last_update_time/initial_upload_time/file_number/file_name`，`order=asc|desc`（默认 last_update_time desc）；非法排序字段 422。
- 例外：版本列表、签名列表、审批步骤、角色/权限列表为小集合，返回**数组**（API.md 明确标注）；其余集合一律分页。

### 10.2 文件检索

参数（全部可选、可组合）：`keyword`（同时模糊匹配 file_name/file_number/process_step/creator 姓名）、`file_number`、`file_name`、`process_step`、`process_code`、`creator_id`、`creator_name`（模糊）、`status`（可多值逗号分隔）、`upload_date_start`/`upload_date_end`（`YYYY-MM-DD`，按 initial_upload_time 闭区间，含当日）、`page/size/sort/order`。

实现：单条 `select(ProcessFile).join(User, creator_id)` 构造条件；`count(*)` 单独查询；LIKE 用转义（`% _ ` 转义）；日期用 `[start 00:00:00, end+1day 00:00:00)`；其中 `YYYY-MM-DD` 按业务时区 `CATALOG_TZ`（默认 Asia/Shanghai）解释，先取业务日 00:00 再转换为 UTC naive 区间（与 API.md §0.1/v1.0.1 口径一致）。

### 10.3 文件可见性（详情/下载/日志）

- 状态 1（草稿）：仅 creator/uploader、admin、当前流程审批人可见。
- 状态 2/3：creator/uploader、当前流程审批人、admin 可见；其他登录用户不可见。
- 状态 4/5：所有登录用户可见（工艺文件受控公开）。
- 状态 0：任何人不可见（admin 通过全量日志追踪）。
- 列表接口先按可见性过滤再 `count(*)`/分页，禁止先分页后过滤；不可见对象（详情/下载/日志/签名/流程）统一返回 **404 FILE_NOT_FOUND**（不区分不存在与无权限，避免探测），列表只返回可见集合。

### 10.4 性能

编号/名称/工序/创建人/状态+更新时间均有索引；count 查询避免 join 多余表；分页使用 `offset/limit`（数据量小，无需 keyset）。

---

## 11. 安全设计

| 域 | 措施 |
| --- | --- |
| 认证 | JWT HS256，`SECRET_KEY` 仅环境变量（≥32 字符，生产缺失拒绝启动）；`exp`=ACCESS_TOKEN_EXPIRE_MINUTES（默认 120）；校验 `sub`/`uid` + 用户存在且活跃；401 统一 `AUTH_TOKEN_INVALID`，过期 `AUTH_TOKEN_EXPIRED` |
| 密码 | bcrypt（`bcrypt.hashpw`，cost 12）直接哈希，不用 passlib；登录失败统一"用户名或密码错误"；改密校验旧密码、拒绝新旧相同；密码长度 6-72 字节（bcrypt 上限） |
| 授权 | 每个写接口 `require_permission`；资源级 owner/审批人校验；不可越权查看草稿；用户管理禁止自禁/删最后一个 admin |
| 上传 | 扩展名白名单（配置项），大小上限（默认 50MB，分块读边写，超限删除临时文件并 413）；服务端生成 UUID 文件名，绝不使用客户端文件名拼接路径；中文/特殊字符名仅存 DB 元数据；按 `UPLOAD_DIR/yyyy/mm/uuid.ext` 落盘；同用户 2 秒上传冷却（内存字典） |
| 下载/路径穿越 | 只接受 `file_id + version`；路径 = `UPLOAD_DIR/相对路径`，`Path.resolve()` 后必须 `is_relative_to(UPLOAD_DIR.resolve())`，否则 403；不挂载 uploads 静态目录；Content-Disposition 使用 RFC 5987 编码，避免头注入 |
| 越权下载 | 下载前执行 §10.3 可见性校验；删除态/审核态一律限制；记录 download 日志（用户/IP/版本） |
| CORS | `ALLOWED_ORIGINS` 逗号分隔；生产 `* ` 与 `allow_credentials` 二选一（默认不允 credentials）；默认 dev 允许 localhost:3000/5173/8000 |
| 配置 | `.env` 不入库（.gitignore 已含）；`.env.example` 只放占位；DEBUG 默认 false；日志不打印密码/token/正文 |
| SQL 注入 | 全 ORM 参数化；LIKE 输入转义；排序字段白名单 |
| 错误信息 | 生产不返回堆栈；500 统一 `INTERNAL_ERROR` 并记录 request_id；业务错误码见 API.md |
| 审计 | 所有写操作 + 下载/登录成功失败记日志（`file_operation_logs`，`target_type` 区分 file/user/auth/catalog）；IP 取 `X-Forwarded-For` 首段或 `request.client.host` |
| 依赖安全 | requirements 锁定主版本；不引入 python-jose/passlib 等重复/冲突依赖 |
| 部署 | Docker 非 root 运行、上传目录卷挂载、数据库口令环境变量；生产 HTTPS 由反代终止 |

---

## 12. 任务分解（WBS）

### 12.1 组织

| 角色 | 人 | 负责 | write scope |
| --- | --- | --- | --- |
| Lead | lead | 集成、验收（含原 chief 评审职责）、git、对外汇报 | — |
| 项目经理 | pm | PLAN/API 契约、计划评审组织 | docs/PLAN.md、docs/API.md |
| 后端 | backend | 全部后端实现、requirements.txt（运行依赖） | 代码目录（见任务板 task-2）、requirements.txt |
| 前端 | frontend | web/ 静态界面 | web/ |
| 测试 | qa | tests/、pytest.ini、冒烟、requirements-dev.txt | tests/、pytest.ini、requirements-dev.txt |

### 12.2 WBS 与验收标准

> 任务板已有 T1(backend)/T2(frontend)/T3(qa)。建议 Lead 按下列子任务拆分跟踪；编号 T1.x 为 backend 子任务。

| 编号 | 任务 | 负责 | 依赖 | 交付物 | 验收标准 | 预估 |
| --- | --- | --- | --- | --- | --- | --- |
| T1.1 | 基础设施修复：config/database/main/run/requirements/.env.example | backend | — | 可启动骨架 | `python run.py` 启动无异常；`/health` 200 且 db ok；SQLite 自动建表；CORS 来自配置；缺 SECRET_KEY 时生产拒绝启动 | 3h |
| T1.2 | 模型重构 + 种子：models/*（file_status int、catalog、signature、sequence）、init_data.py 异步幂等 | backend | T1.1 | 新表 + 种子 | 5 角色 9 权限矩阵正确；演示账号可登录；重复执行不重复插入 | 4h |
| T1.3 | 异步全链路改造 + 统一异常/分页 + auth（登录/注册/me/改密） | backend | T1.2 | crud/dependencies/routers 异步化 | 登录/me 200；缺 token 401；错误结构 `{code,message}`；无 coroutine 警告 | 6h |
| T1.4 | RBAC：permissions 依赖、用户/角色/权限管理接口 | backend | T1.3 | 5 个用户/角色接口 | engineer 调管理接口 403；admin 全通；禁用用户后旧 token 请求 403 | 3h |
| T1.5 | 文件核心：编号、上传（分块/校验/冷却）、列表搜索分页、详情、更新升版、软删除、版本列表 | backend | T1.3 | 文件 CRUD 接口 | 上传后编号符合 `CODE-YYYYMM-NNNN`；并发 10 上传编号唯一；多条件搜索 total 正确；状态 2/3 更新 409；删除后不可见；同工序代码下重名（忽略大小写/空白）409；软删后同名可复用 | 8h |
| T1.6 | 下载安全：鉴权下载、版本下载、路径校验、下载日志 | backend | T1.5 | 下载接口 | 无 token 401；越权草稿 404；`version=1.0.0` 规范；路径穿越参数被拒 | 2h |
| T1.7 | 审批状态机：提交/审核/批准/驳回/归档/签名/流程查询/待办 | backend | T1.4、T1.5 | approval service + 接口 | 正常链 1→2→3→4→5；两条驳回路径均回 1；重复审批 409；签名数量/内容正确；非审批人 403；同一审批人并发/连续两次仅一次生效；驳回分支需 reject 权限 | 8h |
| T1.8 | 文件清单：快照服务、手动刷新、历史快照、每日 0 点调度 | backend | T1.7 | catalog 接口 + scheduler | 归档后清单出现新条目；手动刷新生成快照且条目数正确；调度时间计算单测通过；清单条目可下载 | 5h |
| T1.9 | 操作日志 + 统计概览 + /ui 挂载 + README/Dockerfile/compose | backend | T1.5、T1.7 | 日志/统计接口、部署文件 | 日志分页筛选正确；统计数字与 DB 一致；`/ui/` 可打开；Docker 构建文档可照做 | 4h |
| T1.10 | 全量自测与缺陷修复（响应 qa 报告） | backend | T1.9 | 修复记录 | pytest 全绿；冒烟脚本通过 | 持续 |
| T2.1 | 前端骨架：登录页、主框架、api.js（token/401 跳转/统一错误）、样式 | frontend | T1.3（可先写 mock） | web/ 基础页 | 登录成功进入主界面；401 自动回登录；中文文案 | 4h |
| T2.2 | 文件管理页：列表/搜索/分页/上传进度/详情/版本/下载/更新/删除/提交审核 | frontend | T1.5、T1.6 | 页面 + 联调 | 按 API.md 完成全部操作；错误提示为中文 code 对应文案 | 6h |
| T2.3 | 审批页：待办（审核/批准）、通过/驳回弹窗、流程与签名查看；清单页（刷新/下载）；用户管理页；日志页；概览页 | frontend | T1.7、T1.8、T1.9 | 页面 + 联调 | 两种待办均能处理；清单可手动刷新并下载；管理页仅 admin 可见 | 6h |
| T3.1 | 测试基座：conftest（临时 SQLite、ASGITransport、种子、token 工厂）、pytest.ini | qa | T1.3 | tests/conftest.py | 单用例可独立跑；顺序无关 | 3h |
| T3.2 | 用例：认证/RBAC/用户管理/上传编号/版本/搜索分页/审批状态机/下载安全/清单/日志/软删除/统计 | qa | T1.5、T1.7、T1.8、T1.9 | 11 个测试文件 | 覆盖 API.md 全部接口；关键异常码覆盖；必测：并发 10 上传编号唯一、并发审批仅一次生效、每角色 403/404、软删全链路、路径穿越、日期边界、调度 next_run_at、无 token/过期/禁用 token | 10h |
| T3.3 | 进程级冒烟：启动 uvicorn → curl 全流程脚本 | qa | T1.9 | scripts/smoke.py 或 tests/test_smoke.py | 一条命令跑通登录→…→下载 | 3h |
| T3.4 | 复测与结论 | qa | T1.10 | 测试报告（消息/文档） | 全绿；失败项有复现步骤 | 持续 |
| T4.1 | 计划/契约评审 + 代码抽查 + docs/REVIEW.md（评审职责并入 Lead） | lead | T1.1 起 | docs/REVIEW.md | 覆盖度、越权、路径、并发、状态机问题清单 | 4h |
| T5.1 | 集成、diff 汇总、git 提交/PR、用户评审 | lead | 全部 | 变更摘要 | 用户确认 | 4h |

### 12.3 关键路径与并行

- 关键路径：T1.1 → T1.2 → T1.3 → T1.5 → T1.7 → T1.8 → T3.2/T3.3 → T5.1。
- 并行：T1.4 与 T1.5 可并行（接口边界：权限依赖先合入）；frontend 在 T1.3 后即可按 API.md 用 mock 开发，T1.5/T1.7/T1.8 完成一段联调一段；qa 在 T1.3 后建基座，随接口完成逐步补用例。
- 接口冻结：API.md v1.0.x（当前 v1.0.3）即基线。**变更流程（强制）**：①backend/frontend/qa 发现必须变更时，先在 API.md §13「变更记录」追加一行（版本 v1.0.x、日期、路径/字段/错误码、原因、提出人）；②同时消息 pm 与 lead，由 pm 更新契约正文并通知三方；③文档与代码需在 30 分钟内同步，避免返工；④**禁止静默改契约**，文档未更新的接口变更视为缺陷，Lead 抽查时按 P0 记录。
- 契约变更不改变已冻结的路径与语义时（仅补充字段说明/示例），pm 更新文档即可；破坏性变更（删字段/改路径/改错误码）必须经 lead 确认后再实施。

### 12.4 协作规则（重申）

1. 只写自己范围；跨范围改动先消息。
2. 禁止 git 写操作。
3. 任务板认领/完成；进展与阻塞消息 lead，消息格式：`[状态] 任务号 结论/阻塞/需要谁在何时做什么`。
4. 代码注释/API 提示/UI 文案中文。
5. 不留 TODO/占位；接口未实现就返回明确 501 不允许。

---

## 13. 里程碑

| 里程碑 | 内容 | 验收 | 依赖 |
| --- | --- | --- | --- |
| M0 契约冻结 | PLAN.md + API.md 完成，Lead 确认 | 文档评审通过 | pm |
| M1 可启动 | T1.1+T1.2+T1.3：启动、建表、种子、登录/me | uvicorn 启动 + curl 登录成功 | backend |
| M2 文件闭环 | T1.4-T1.6：RBAC、上传/列表/搜索/更新/下载/删除/版本 | curl 完成文件 CRUD + 权限 403 验证 | backend |
| M3 审批闭环 | T1.7：提交→审核→批准→归档、驳回、签名、待办 | 全状态机用例通过 | backend |
| M4 清单闭环 | T1.8：自动+手动刷新、历史快照、下载链接 | 归档后清单含新文件；手动刷新成功 | backend |
| M5 可演示 | T1.9+T2.x：UI、日志、统计、README/Docker | 浏览器完成全流程演示 | frontend/backend |
| M6 可交付 | T3.x + T4.1：pytest 全绿、冒烟通过、评审通过、diff 汇总 | Lead 出具交付说明 | qa/lead |

---

## 14. 风险与应对

| 风险 | 可能性 | 影响 | 应对 |
| --- | --- | --- | --- |
| 异步改造引入大量回归（全局 500） | 高 | 高 | T1.3 一次性改完，禁止新旧混用；先做登录冒烟再继续；qa 基座尽早建立 |
| SQLite 与 MySQL 行为差异（锁/枚举/日期/大小写） | 中 | 中 | 开发用 SQLite 但 SQL 只用通用能力；状态用 int；日期统一 UTC；并发编号测试覆盖；MySQL 配置保留并在 README 说明 |
| 并发编号重复/唯一键冲突 | 中 | 高 | 序列表 + 唯一约束 + 重试；单测并发 10/20 上传 |
| 审批状态机遗漏路径导致卡单 | 中 | 高 | 状态迁移表逐条实现 + 用例覆盖（含重复提交、越权审批、已归档更新）；条件更新保证并发仅一次生效 |
| 审批人被禁用导致待办无人处理 | 中 | 中 | 本轮不做改派；提交/审核通过时校验审批人活跃，失效则拒绝并提示；卡单由驳回后重新提交解决（Lead 决策，见 §1.3） |
| 每日调度与多 worker 重复刷新 | 中 | 低 | `ENABLE_SCHEDULER` 开关 + 单实例说明；刷新幂等（同秒复用快照） |
| 前端与后端契约漂移 | 高 | 中 | API.md 冻结 + frontend 先 mock + 联调日集中修；错误码统一 |
| Windows 路径/编码问题（GBK、路径分隔符） | 中 | 低 | 全部 `pathlib`；响应 UTF-8；不依赖 shell 脚本 |
| 依赖安装失败（bcrypt/PyJWT 版本） | 低 | 中 | requirements 钉版本；Lead 已装好虚拟环境，backend 不擅自升级 |
| 项目时间紧、任务交叉 | 高 | 中 | 严格 write scope；并行任务边界清晰；Lead 每日集成一次 |
| 文件丢失/上传目录被清 | 低 | 高 | 下载 404 明确错误；README 说明 uploads 需持久卷；Docker volume |

---

## 15. 验收清单（DoD）

### 15.1 功能

- [ ] 登录/注册/me/改密；禁用用户不能登录，旧 token 失效。
- [ ] RBAC：engineer 不能审核/批准/管理用户；leader 只能审核；manager 只能批准；archivist 只能归档/刷新清单；admin 全通。
- [ ] 上传：编号 `CODE-YYYYMM-NNNN` 唯一；扩展名/大小校验；中文文件名正常。
- [ ] 列表/搜索：文件名、编号、编制人、工序、状态、日期区间组合筛选；分页 total/pages 正确。
- [ ] 详情/版本：版本历史完整；指定版本下载正确。
- [ ] 更新：patch/minor/major 升版规则正确；审核中更新 409。
- [ ] 审批：提交→审核→批准→归档；审核驳回、批准驳回均回草稿并可重新提交；待办正确；签名记录完整。
- [ ] 并发/幂等：同一审批人并发两次审核/批准仅一次生效（409 APPROVAL_ALREADY_DONE）；并发 10 上传编号唯一。
- [ ] 重名规则：同 process_code 下重名（忽略大小写/首尾空白）409；软删除后同名可复用；并发同名仅一个成功。
- [ ] 文档中无任何真实口令，仅出现变量名/占位符（如 `<SEED_PASSWORD>`）。
- [ ] 统计 by_status 键符合 API §9.3 映射；null 语义符合 API §9.4。
- [ ] 下载：无 token 401；越权草稿 404；版本缺失 404；路径参数不能穿越。
- [ ] 软删除：删除后列表/详情/下载/统计/清单均不可见；编号不复用。
- [ ] 文件清单：归档自动刷新；手动刷新；每日 0 点调度函数正确；条目 download_url 可下载。
- [ ] 日志：全部写操作与下载有记录；分页筛选正确。
- [ ] 统计：总数/状态分布/我的待办/最近刷新/最近操作正确。
- [ ] UI：登录、文件、审批、清单、用户、日志、概览可用，中文文案，错误提示友好。
- [ ] 部署：SQLite 一键启动；MySQL 配置文档；Dockerfile/compose 可构建（不强制本轮实际构建成功但文档必须可执行）。

### 15.2 质量

- [ ] `pytest` 全绿，无 skip 掩盖。
- [ ] 无同步 Session 残留、无 `datetime.utcnow()`、无 `.dict()`、无 passlib/python-jose。
- [ ] 无 TODO/FIXME/占位实现。
- [ ] 所有路由有响应模型、错误码、权限标注。
- [ ] 文档与实现一致（API.md 与 OpenAPI 字段一致）。
- [ ] git diff 无越权修改（每人只改自己范围）。

---

## 16. 变更记录

| 版本 | 日期 | 变更 | 作者 |
| --- | --- | --- | --- |
| v1.0 | 2026-11-11 | 初版：现状问题清单、架构决策、数据模型、状态机、RBAC、编号/版本、清单、搜索分页、安全、WBS、里程碑、风险、DoD | pm |
| v1.0.2 | 2026-11-11 | P0/P1 修订：种子口令占位符化（SEED_PASSWORD 注入）、字段溯源（意见/说明/approved_at 派生）、文件重名规则（name_key 唯一索引+归一化+软删复用+并发兜底）、审批并发/幂等（条件更新+单事务）、reject 权限分支、时间/前端/分页/可访问性口径、out-of-scope（工序分工/改派/编制人分离）、12.1 职责与 requirements-dev 归属 | pm |
| v1.0.3 | 2026-11-11 | 二轮修订：CatalogItem.approved_at 派生源改为 process_files.approved_at（回退 archived_at）、catalog_items 唯一约束、快照复用仅同刷新方式+操作人、0 字节文件拒绝（FILE_EMPTY）、审批人失效回退、prod 环境默认值（ALLOW_REGISTER/SEED_DEMO_USERS/SECRET_KEY）、评审职责并入 Lead | pm |

