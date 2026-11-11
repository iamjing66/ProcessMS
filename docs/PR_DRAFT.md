# 工艺文件管理系统 改造 PR 描述（定稿候选 v0.2）

> 状态：v0.2 定稿候选。REVIEW §11 结论"通过，可交付"：P0×4 与 IR-01 清零，168 项自动化用例全绿 + 进程级冒烟 PASS；backend/frontend/qa 已收尾。评审通过后即可作为 PR 描述提交。
> 分支：`dhs_bot` → `main`；依据：工艺文件管理系统.md（需求）、docs/PLAN.md v1.0.3、docs/API.md v1.0.3。

---

## 1. 概述

把原有"模型齐全、但同步/异步混用且核心流程缺失"的半成品，修复为**可运行、可测试、可演示**的工艺文件管理系统：完成 上传 → 组长审核 → 主管批准 → 签名留痕 → 资料员归档 → 自动/手动更新文件清单 → 多条件检索 → 审计日志 的完整闭环，并补齐 RBAC、受控下载、软删除、统计概览、Web 管理界面与自动化测试。

- 技术栈：FastAPI + SQLAlchemy 2.0（全异步）+ MySQL（生产，aiomysql）/ SQLite（开发测试，aiosqlite）+ Pydantic v2 + PyJWT + bcrypt；前端为纯静态 HTML/CSS/JS（无 npm 构建链）。
- 兼容性：保留 `/api` 前缀与既有模型字段语义；无外部调用方，故接口属"补齐"而非破坏性变更；状态枚举由"双枚举"统一为 int（0-5），响应新增 `file_status_text` 便于展示。
- 数据库：无生产存量数据，采用 `create_all` + 幂等种子；生产后续变更由 DDL/后续 Alembic（P2）接管。

## 2. 主要变动项

### 2.1 P0 修复（可运行性）
- 全链路异步化：`database.py`（async engine/async_sessionmaker）、`crud/*`、`dependencies/*`、`routers/*` 全部 `async/await`，消除"异步 DB + 同步调用"必崩问题。
- 启动流程：`main.py` 改用 lifespan——建目录 → 建表 → 幂等种子 → 按配置启动清单调度；import 无副作用；`run.py` 关闭 reload 双初始化。
- 配置：`config.py` 迁移到 pydantic-settings v2；`.env` / 环境变量；dev 默认 SQLite、prod 显式 MySQL；SECRET_KEY 生产缺失拒绝启动；CORS 走配置。
- 依赖：重写 `requirements.txt`（新增 aiomysql/aiosqlite/pydantic-settings/PyJWT/bcrypt/tzdata 等），新增 `requirements-dev.txt`、`pytest.ini`、`.env.example`。
- 状态枚举：新增 `models/enums.py`，文件状态统一 int（0 删除/1 草稿/2 待审核/3 待批准/4 已批准/5 已归档），审批流 0/1/2、步骤 0/1/2；ORM 用 SmallInteger，schema 输出 int + 中文文案。

### 2.2 数据模型（`models/`）
- 新增：`models/approval.py`（approval_flows / approval_steps / file_signatures）、`models/catalog.py`（catalog_snapshots / catalog_items / file_number_sequences）、`models/enums.py`。
- 调整：`process_files`（process_code、name_key、approved_at、archived_at/by、deleted_at/by、状态 int、索引）、`file_versions`（file_hash、`(file_id,version)` 唯一）、`file_operation_logs`（target_type/target_id/user_agent、组合索引、file_id 可空）、`approval_flows`（version、planned_approver_id、reject_reason）、`approval_steps`（`(flow_id,step_number)` 唯一）、`users`（updated_at）。
- 种子（`init_data.py`，幂等）：5 角色（admin/engineer/leader/manager/archivist）、9 权限（upload/update/delete/review/approve/reject/archive/catalog_manage/user_manage）及矩阵；演示账号仅在 `ENV=dev` 或 `SEED_DEMO_USERS=1` 时创建，口令只读 `SEED_PASSWORD`。

### 2.3 业务能力
- 文件：上传（扩展名白名单、50MB 上限、分块落盘、SHA-256、UUID 存储、空文件 400 FILE_EMPTY、同用户 2s 冷却）、列表/多条件检索分页、详情（含 allowed_actions/approval/latest_version/signatures）、更新（元数据/升版 major/minor/patch，状态 2/3 锁定 409 FILE_LOCKED，4/5 更新必带新文件并回草稿）、软删除、版本列表与指定版本下载。
- 编号：`{process_code}-{YYYYMM}-{NNNN}`，`file_number_sequences` 按 `(process_code, YYYYMM)` 原子自增 + 唯一约束 + 冲突重试；编号不可变、不复用。
- 版本：`Vx.y.z` 校验与递增；唯一 `(file_id, version)`。
- 重名：同 `process_code` 下未删除文件名唯一（去首尾/压缩空白/英文大小写折叠），`name_key` 唯一索引兜底软删复用与并发，409 FILE_NAME_DUPLICATED。
- 审批：提交审核（新建 flow+step1）、审核通过/驳回、批准通过/驳回、归档、签名留痕；step2 在审核通过时创建；审批意见落 approval_steps.approval_comment + file_signatures.remark；提交/归档说明落 operation_details；步骤条件更新 + 单事务，重复/并发 409 APPROVAL_ALREADY_DONE；待办与流程/签名查询。
- 归档与清单：归档自动刷新 + 手动刷新 + 每日 0 点（`CATALOG_TZ`）asyncio 调度；快照 `catalog_snapshots` + 条目 `catalog_items` 两步存储；条目 `approved_at` 由 `process_files.approved_at` 派生（回退 archived_at）；条目含鉴权下载链接；快照号 `QD-YYYYMMDDHHMMSS`，同秒复用限"相同刷新方式+操作人"。
- RBAC：`dependencies/permissions.py` 权限依赖（admin 短路）+ 资源级校验（本人/当前审批人）；用户管理（建用户/改角色/禁用，自禁与最后 admin 保护）；角色/权限查询。
- 日志与统计：全量操作日志分页筛选（仅 user_manage）、单文件日志；概览统计（文件状态分布、我的待办、清单刷新、用户数、最近操作）。
- 安全：移除 `/uploads` 静态挂载，下载走鉴权接口 + 路径 resolve 校验 + RFC 5987 头；bcrypt 直接哈希、JWT 过期/禁用/非法区分；下载/登录/全部写操作审计（IP/UA）；错误结构统一 `{code,message,detail}`；排序白名单与 LIKE 转义。

### 2.4 前端（`web/`，纯静态）
- `web/index.html`（登录）+ `web/app.html`（单页 tab 主框架）：概览、文件管理（列表/搜索/分页/上传进度/详情/版本/下载/更新/删除/提交审核）、待办审批（审核/批准/驳回）、文件清单（刷新/下载）、用户管理（admin）、操作日志、概览；共享 `api.js`（Bearer、401 跳转、统一错误）、`upload.js`（XHR 进度）。
- 后端 `/ui` 挂载，`/` 302 到 `/ui/`。

### 2.5 测试与工程
- `tests/`：15 个用例模块（auth/rbac/users/upload/versions/search/pagination/approval/catalog/download/delete/logs/stats/units/health）+ conftest/helpers + smoke（进程级），基于临时 SQLite + httpx ASGITransport + 真实路由与权限；`tests/smoke` 进程级冒烟脚本；`.github/workflows/ci.yml`。
- 文档：`docs/PLAN.md`（v1.0.3，范围/问题清单/架构/模型/状态机/RBAC/编号版本/清单/搜索分页/安全/WBS/里程碑/风险/DoD）、`docs/API.md`（v1.0.3，37 个接口契约/错误码/数据字典）、`docs/REVIEW.md`（评审与实现问题跟踪）。

## 3. 接口（详见 docs/API.md）

统一约定：`/api` 前缀、JSON、Bearer JWT、错误体 `{code,message,detail}`（40+ 错误码）、分页 `{items,total,page,size,pages}`（默认 page=1/size=10，上限 100）、时间 UTC ISO8601、日期查询按业务时区 `CATALOG_TZ` 解释。

新增/重写 37 条路由（与 OpenAPI 实测一致）：
- 认证：POST /api/auth/login、/register、/change-password；GET /api/auth/me
- 用户/角色：GET/POST /api/users、GET/PUT/DELETE /api/users/{id}、PUT /api/users/{id}/roles、GET /api/roles、GET /api/permissions
- 文件：POST /api/files/upload；GET /api/files；GET/PUT/DELETE /api/files/{id}；GET /api/files/{id}/download；GET /api/files/{id}/versions、/versions/{version}/download；GET /api/files/{id}/signatures、/approval、/logs
- 审批：POST /api/files/{id}/submit-review、/review、/approve、/archive；GET /api/approvals/pending、/flows、/flows/{id}
- 清单：GET /api/catalogs、/catalogs/snapshots、/catalogs/snapshots/{id}；POST /api/catalogs/refresh
- 日志/统计/健康：GET /api/logs、GET /api/stats/overview、GET /health

## 4. 测试与验证证据（截至本稿）

| 项 | 命令/方式 | 结果 |
| --- | --- | --- |
| 应用导入 | `python -c "import main"` | 通过（lifespan 无 import 副作用） |
| 自动化测试 | `python -m pytest -q` | **168 passed, 1 deselected（smoke）；Lead 118.52s / PM 127.96s 复跑一致** |
| 路由契约对照 | `app.openapi()["paths"]` vs API.md §11 | 37 条完全一致（PM 复核） |
| 忽略规则 | `git check-ignore` | `.env` / `data/` / `uploads/` 均被忽略，无敏感/运行产物入库 |
| 进程级冒烟 | `python tests/smoke/run_smoke.py` | **PASS**：真实 uvicorn + SQLite 随机端口，5 角色登录→上传→提交→审核→批准→归档→清单→下载→手动刷新→统计→日志（backend 31/31，PM 独立复跑 PASS，REVIEW 复核） |
| ASGI 冒烟 | backend 自测 | 59/59 通过（真实路由/权限/数据库） |
| 前端联调 | `/ui/` 实测（REVIEW §11.6） | `/` 302、`/ui/` 200、`/ui/app.html` 200、`/ui/js/api.js` 200；16 个 JS `node --check` 通过；未做浏览器视觉自动化（用户评审时实测） |
| 评审结论 | docs/REVIEW.md §11 | **通过，可交付**；P0×4、IR-01~13 全部 Closed；残余风险见 REVIEW §11.4 |

覆盖重点（qa 用例）：认证/令牌/权限矩阵、越权 403/404、上传编号唯一与重名、版本规则、审批状态机与驳回、下载安全（越权/版本/路径）、搜索分页与日期边界、清单刷新与派生字段、软删除全链路、日志与统计、调度纯函数。

## 5. 风险与已知限制

1. **Docker 未实测构建**：Dockerfile/docker-compose.yml 已提供（另含 .dockerignore、.github/workflows/ci.yml；本机无法验证构建，见 REVIEW P2-8），README 已补充启动/MySQL/演示说明；验收以本地 venv + SQLite 为准。
2. **MySQL 运行路径未实测**：本机无 MySQL 服务，依赖为 aiomysql（asyncmy 可选）；SQLite 全流程已验证，生产切换需按 `.env.example` 配置并在目标环境复核。无 Alembic，存量库需重建或手工 DDL。
3. **审批并发**：已闭环（REVIEW IR-01 Closed）——条件更新 + rowcount 校验 + 单事务，并发用例通过。
4. **reject 权限分支**：已按决策实现——pass 分支要求 review/approve，reject 分支要求 reject，且须为当前步骤审批人；用例已覆盖。
5. 每日 0 点调度为进程内单任务，**单 worker 部署**；多 worker 需 `ENABLE_SCHEDULER=false` 或外置定时任务（README 说明）。
6. 范围外（已写入 PLAN §1.3）：PDF/Office 转换、通知、单用户互踢、分片上传、流程可视化配置、审批人自动改派、工序分工、编制人/上传人分离、CSV 导出、Alembic。
7. 快照历史保留不清理；旧快照中已更新/软删文件的下载链接会 404（下次刷新剔除），演示需说明。
8. 登录失败无锁定/限流，上传仅 2s 冷却；生产建议网关层限流（记录为 P2）。
9. **定时/CI/测试加速**（REVIEW §11.4）：每日 0 点真实触发未等待（纯函数单测覆盖）；上传冷却为进程内字典，多 worker 不共享；GitHub Actions 未在 GitHub 实跑（本地等价命令通过）；测试 bcrypt cost=4 仅加速，生产 cost=12。

## 6. 评审建议（Reviewer Checklist）

- [ ] 干净 SQLite：`python run.py` → `/health` → `/ui/` 登录可演示。
- [ ] 全流程：上传 → 提交 → leader 审核 → manager 批准 → archivist 归档 → 清单刷新/下载 → 日志/统计。
- [ ] 越权：engineer 审核/批准/管理用户 403；跨用户草稿 404；下载不可见文件 404。
- [ ] 并发：10 并发上传编号唯一；同一审批并发仅一次生效。
- [ ] 重名：同 process_code 大小写/空白差异 409；软删后同名可复传。
- [ ] 安全：无静态 /uploads、路径穿越、JWT 过期/禁用、文档无真实口令。
- [ ] `python -m pytest -q` 全绿；`.env`/`data`/`uploads` 不入库。

## 7. 变更记录

| 版本 | 日期 | 说明 | 作者 |
| --- | --- | --- | --- |
| v0.1 | 2026-11-11 | 初稿：基于已落地实现与 157 项测试结果整理 | pm |
| v0.2 | 2026-11-11 | 定稿候选：同步 REVIEW §11 结论（通过可交付、P0/IR Closed）、168 用例、进程冒烟 PASS、前端联调与残余风险 | pm |
