# 工艺文件管理系统 评审记录（REVIEW）

| 项 | 值 |
| --- | --- |
| 评审人 | 总负责人（chief） |
| 评审对象 | docs/PLAN.md（645 行）、docs/API.md（1254 行）、现有代码基线（1274 行） |
| 评审时间 | 2026-11-11 10:25（Asia/Shanghai） |
| 评审方法 | 通读需求文档/PLAN/API；逐文件阅读基线代码；用项目 venv 实测依赖与导入；后续实现阶段按本文件 §6 抽查实际代码与运行结果 |
| 结论 | **有条件通过（可进入实现）**：架构与范围总体合理、覆盖度较高；但存在 **4 个 P0 契约/合规项**与若干 P1，须在接口冻结前修订，否则会造成实现歧义或安全合规问题 |

---

## 0. 结论摘要

1. **需求覆盖**：工作流程（上传→审核→批准→签名→归档→清单）、人员/RBAC、文件字段、软删除、版本、搜索、清单（手动+每日自动+归档触发）、日志、JWT 均已覆盖，且明确列出了 Out of Scope。
2. **架构**：异步全链路、lifespan、统一异常/分页、服务层、SQLite 开发 + MySQL 生产、受控下载、序列表发号、后台调度等决策合理，可直接支撑实现。
3. **阻断项（P0）**：明文演示口令入文档（违反项目规则 6）；API 部分字段无数据模型落点；文件重名规则未进入模型且与需求"文件名称唯一"不一致；审批动作的并发/幂等未定义。
4. **风险点（P1）**：审批人失效导致卡单；可见性 404/403 表述矛盾；reject 权限码悬空；编制人/上传人语义；工序分工未答复；时间口径未定；前端 iframe 多页范围风险；测试有效性要求需前置。
5. **放行条件**：P0 全部修订并回执 → P1 由 Lead 决策（修/明确不做）→ 进入实现。实现完成后按 §6 抽查并在本文件追加"实现评审"章节。

---

## 1. 需求覆盖度核验

| 需求条目（工艺文件管理系统.md） | 计划/契约覆盖 | 结论 |
| --- | --- | --- |
| 编制、上传工艺文件 | PLAN §6.2 #1、API §3.1 | ✅ |
| 是否需要转 PDF | PLAN §1.3 明确范围外 | ✅（隐含决策，需用户知悉） |
| 组长审核 | PLAN §6.2 #3/#4、API §3.10、RBAC leader.review | ✅ |
| 主管批准 | PLAN §6.2 #5/#6、API §3.11、RBAC manager.approve | ✅ |
| 添加签名（统一/分步） | PLAN §6.4 自动在节点签名、file_signatures 表、API §3.13 | ✅（采用"节点自动文本签名"的决策合理） |
| 资料员归档 | RBAC archivist.archive、PLAN §6.2 #7、API §3.12 | ✅ |
| 文件清单手动+自动+确认 | PLAN §9、API §5、每日 0 点调度 + 归档触发 + 手动按钮 | ✅ |
| 文件本地存储、DB 存相对路径 | PLAN D6、§5.2 storage_path、API §3.6 | ✅ |
| 清单分步存储、链接可打开 | catalog_snapshots + catalog_items、download_url | ✅ |
| 人员信息（工号/用户名/密码） | PLAN §5.1/§5.2、API §2 | ✅ |
| 登录状态/单用户登录 | PLAN §1.3 明确不做（JWT 无状态） | ⚠️ 需确认（需求中为疑问句，建议认可该取舍） |
| 权限：上传/审核/批准/归档/删除/更新/驳回 | PLAN §7.1/§7.2、API §11 矩阵 | ✅（reject 码见表外问题 P1-2） |
| 分工：工序分工 | **PLAN/API 均未提及，也未列入 Out of Scope** | ❌ 缺口（P1-5） |
| 文件字段：名称/版本/日期/编号/人员/内容/工序 | PLAN §5.2、API §3.2 | ✅（日期为自动时间戳，无手动日期字段，建议在 PLAN 记录该决策） |
| 版本号大/小版本规则、版本冲突检查 | PLAN §8.3、API §3.4 version_type | ✅ |
| 编号唯一 | PLAN §8.2 序列表 + unique + 重试 | ✅ |
| 文件名称唯一（需求原表） | API §3.1/§10 要求"同工序代码下同名未删除"唯一；PLAN 模型/规则缺失 | ⚠️ 契约缺口（P0-3） |
| 文件状态值/驳回回退 | PLAN §6.1/§6.2、API §0.6.1 | ✅ |
| 假删除/真删除 | PLAN §6.5 软删除、API §3.5 | ✅ |
| 查找：文件名/编号/编制人/工序 | PLAN §10.2、API §3.2（+状态/日期） | ✅ |
| 操作日志/审计 | PLAN §11、file_operation_logs、API §6/§3.15 | ✅ |
| 登录认证（JWT） | PLAN D7/§11、API §1 | ✅ |
| 部署/文档 | PLAN §4/§5.4、README/.env.example/Dockerfile | ✅（Docker 未实测，见 P2） |

**覆盖结论**：主流程与核心字段全覆盖；1 项功能缺口（工序分工）与 1 项契约缺口（文件重名唯一性）需闭环。

---

## 2. P0（阻断：冻结前必须修订）

### P0-1 明文演示口令写入文档，违反项目硬规则
- 位置：`docs/API.md` 第 155、190、243、244、299、1201 行（登录/注册/改密/curl 示例）；`docs/PLAN.md` 第 281 行允许"默认密码出现在 .env.example 与 README 开发说明"。
- 问题：API.md 中的口令即 PLAN §5.4 演示账号的真实初始口令，文档进入仓库/PR 即等价于泄露可用凭据，违反"不要把密钥/密码写入代码或文档"。
- 要求：
  1) API.md 示例统一改占位符（如 `"password": "<密码>"`），curl 示例从环境变量读取；
  2) PLAN §5.4 第 4 条改为：演示账号口令仅通过 `SEED_PASSWORD` 环境变量注入，任何文档只写变量名与占位符，不得出现实际值；
  3) 种子脚本/README/.env.example 严禁硬编码或展示真实口令。
- 责任：PM（文档）/ backend（种子脚本）；回执后由 chief 复核。

### P0-2 API 字段无数据模型落点（approved_at、submit-review comment、archive comment）
- 位置：API §5.0 CatalogItem `approved_at`；API §3.9 请求 `comment`；API §3.12 请求 `comment`；PLAN §5.2 process_files/file_versions/approval_flows/catalog_items 均无对应来源列或取值规则。
- 问题：`catalog_items.approved_at` 是必返字段且可排序，但 PLAN 未定义取值来源；提交审核意见与归档意见同样无落库字段，backend 只能自行猜测（丢失/写错），契约无法验收。
- 要求（三选一并写回 PLAN/API）：
  1) `approved_at` 增加 `process_files.approved_at`（批准通过时写入），提交/归档意见写入对应 flow 或 operation_logs 的 operation_details；
  2) 或明确 `approved_at` 取最近一条 step_number=2 通过时间（查询派生），意见写 operation_details；
  3) 无论哪种，API 文档标注来源与 null 语义。
- 责任：PM 决策 + 文档修订；backend 按修订实现。

### P0-3 文件重名规则未进入 PLAN 且与需求"文件名称唯一"不一致
- 位置：API §3.1/§10 `FILE_NAME_DUPLICATED`（同 process_code 下同名未删除文件）；PLAN §5.2/§8 无该约束、无索引、无并发兜底；需求文档文件表要求"文件名称唯一"。
- 问题：契约要求唯一性但计划没有落点，实现必然是"随手查一下"，并发可穿透；且"同工序代码下唯一"是对需求的收窄，需显式决策。
- 要求：
  1) PLAN 增加重名规则章节（范围 = 同 process_code + 未删除 + 大小写/空白归一化规则；软删后是否可重用；与更新改名/升版的交互）；
  2) 给出实现方式（应用层查重 + 必要的唯一约束/序列化策略 + 并发兜底），并列入 T1.5 验收与 QA 用例；
  3) 若采纳"全库唯一"则同步改 API 描述与错误文案。
- 责任：PM 决策 + backend 实现 + qa 用例。

### P0-4 审批动作并发/幂等未定义（重复审批、双签名风险）
- 位置：PLAN §6.2/§6.3、API §3.10/§3.11 `APPROVAL_ALREADY_DONE`；T1.7 验收标准未包含并发/重复提交。
- 问题：审核/批准是"读状态→校验审批人→写步骤+签名+文件状态+日志"多步操作；双击或两个并发请求可能双写签名/重复推进；SQLite 与 MySQL 行为不同。仅定义错误码不够，需定义原子迁移与幂等实现。
- 要求：
  1) PLAN 明确：步骤状态迁移使用条件更新（如 `UPDATE approval_steps SET approval_status=1 WHERE id=? AND approval_status=0`）或以行锁在同一事务内完成，影响行数=0 时返回 409 `APPROVAL_ALREADY_DONE`；
  2) 文件状态与 flow 状态在同一事务内更新，日志/签名同事务；不得先写签名后校验；
  3) T1.7 验收补充"同一审批人并发/连续提交两次仅一次生效"；qa 必测；
  4) 归档+清单刷新、提交审核+flow/steps 创建同样要求单事务原子性。
- 责任：backend 实现 + PM 补验收条目 + qa 用例。

---

## 3. P1（高优先：冻结前定方案，实现阶段验证）

| 编号 | 问题 | 位置 | 处理建议 |
| --- | --- | --- | --- |
| P1-1 | 文件可见性结论自相矛盾（同一段先说 403、再写统一 404） | PLAN §10.3 第 497 行 | 统一为 404 `FILE_NOT_FOUND`（与 API §0.7 一致），删除 403 表述；同时约束"列表先过滤可见集合再 count/分页" |
| P1-2 | `reject` 权限码在矩阵中授予 leader/manager，但 API 审核/批准接口只校验 review/approve，该权限永不生效 | PLAN §7.1/§7.2 第 353/360-366 行；API §3.10 第 605 行、§3.11 第 643 行 | 二选一：删除 reject 权限码；或 API 明确 result=reject 时同时校验对应步骤权限 + reject 权限。建议删除（避免权限表冗余与歧义） |
| P1-3 | 审批人失效/被禁用后文件卡死（提交时分配、审核通过后 step2 审批人可能已禁用；用户禁用无待办迁移） | PLAN §6.4 第 327 行、§6.5 第 337 行；API §2.6 | 提交与审核通过时校验审批人仍活跃；提供 admin 改派接口（写审计）或明确"仅能驳回后重新提交"；用户禁用接口需提示其待办 |
| P1-4 | 编制人/上传人语义：上传无 creator_id，creator≡uploader，且无工序交接/改编制人能力 | PLAN §6.2 #1 第 305 行；API §3.1 | 明确"creator=uploader、交接不实现"并写入 §1.3，或上传允许指定 creator_id（需权限）。需求区分了上传人与编制人，不能让后端默认猜 |
| P1-5 | "分工-工序分工"未覆盖也未列 Out of Scope | PLAN §1.3 第 49-61 行；需求"人员系统-分工" | 本轮建议列入 §1.3 并注明原因，由 Lead 向用户确认；若必须实现则需新增数据模型与任务，不可装作不存在 |
| P1-6 | 时间口径未定：PLAN D9 写"存 UTC naive 或 aware"二选一未决 | PLAN D9 第 122 行；API §0.1/§0.6 | 写死一种：建议 DB 存 UTC aware/或 naive+统一序列化补 +00:00；日期区间查询按业务时区 Asia/Shanghai 换算；否则会出现 naive/aware 比较 TypeError 或 8 小时偏差 |
| P1-7 | 前端范围失控风险：多页 + iframe 主框架（无构建链）会出现登录态/token/错误处理重复实现 | PLAN D12 第 125 行；API §8.3 | 建议 `login.html` + 单页 `app.html`（hash/tab 切换），共享 `api.js`；上传进度用 XHR（fetch 无 upload progress）；页面优先级：文件→审批→清单→用户/日志/概览（后两者可后置）。iframe 不建议 |
| P1-8 | write scope 重叠：requirements-dev.txt 同属 backend(task-2) 与 qa(task-4) | 任务板 task-2/task-4 writeScopes | Lead 指定单一 owner（建议 backend 维护、qa 只读），避免同时改文件冲突 |
| P1-9 | 测试有效性要求需前置：11 个用例文件的数量不是质量 | PLAN T3.2/§15 | 必测项：并发 10 上传编号唯一、同一审批并发仅一次生效、每角色 403/404 越权、下载不可见/路径穿越、软删后列表/详情/下载/清单/统计均不可见、日期边界、调度 next_run_at 纯函数、无 token/过期/禁用 token；禁止只断言 200、禁止 mock 掉被测路由 |
| P1-10 | 演示口令措辞仍允许写入 README/.env.example | PLAN §5.4 第 281 行 | 收紧为"只出现占位符/变量名；实际口令由 `SEED_PASSWORD` 注入"，见 P0-1 |
| P1-11 | step2 审批人创建时机两处表述不一致（提交时 vs 审核通过时） | PLAN §6.2 #2 第 305 行 vs §6.4 第 328 行；API §3.10 | 统一为"step2 在审核通过时创建并分配主管"（与 API next_approver 一致），修正 §6.2 措辞 |
| P1-12 | 分页默认值不一致：通用 size=10，清单默认 20，日志未标注 | API §0.5.1、§5.1、§6.1 | 统一全局默认或逐接口明确；前端按响应回显值渲染 |
| P1-13 | process_code 草稿可改但 file_number 前缀不可变，二者可能永久矛盾 | API §3.4 第 514 行 | 建议创建后禁止修改 process_code（或仅允许同码 correction）；写入 PLAN 规则与错误码 |
| P1-14 | 统计 by_status 使用英文键（draft/pending_review…），全系统状态为 int + 中文文案 | API §7.1 第 1009-1016 行 vs §0.6.1 | 统一映射并写入数据字典（int↔英文键↔中文），避免前端/后端各写一套 |
| P1-15 | `signature_text` 为派生字段，但多角色用户的"角色名"来源未定义 | API §3.13 第 704/716 行；PLAN §5.2 第 255 行 | 建议持久化 `signature_text`（审批时生成）或定义角色取值优先级（如步骤对应角色 code） |

---

## 4. P2（记录，不阻断；实现/验收时注意）

1. PLAN 第 130 行标题错字："目标目录结构" → "目标目录结构"（低风险，PR 前清理）。
2. API §5.4 快照详情不分页（"条目数受控"），清单条目可能 >100；建议限制或分页。
3. 每次归档都生成新快照 → 快照膨胀；数据量小可接受，建议 README 记录（可后续加同秒/合并策略）。
4. 已归档文件更新回草稿/软删后，旧快照仍含旧条目（下载 404），下次刷新剔除；需在 README 说明，避免演示误解。
5. 登录无失败次数限制/锁定；建议简单失败计数或延迟（成本低）。
6. JWT 无状态：改密/禁用后旧 token 在过期前仍有效（禁用已由每请求查库覆盖，改密不覆盖）；记录风险或引入 password_version claim。
7. 上传内容嗅探/病毒扫描不做（范围外），README 记录。
8. Dockerfile/docker-compose 本机无法验证；不纳入验收阻断，但需人工审查语法与依赖（含 MySQL 驱动 asyncmy）。
9. 本机 venv 无 `asyncmy`（有 `aiomysql`），MySQL 运行路径无法实测；requirements/README 需保证生产可安装，残余风险写入交付说明。
10. `GET /api/files/{id}/approval` 的 "current_flow" 选取规则未定义（最新 flow？进行中优先？）；建议明确为"最近创建的一条 flow，history 为其余"。
11. `operation_type_text`、`approval_status_text`、`refresh_type_text` 映射表未给全；建议在 API 附录补映射，前端不要自造。
12. 文件列表 total 必须先应用可见性过滤再 count（易错点），qa 用例覆盖。
13. `GET /api/users/{id}` 本人可读，但前端非管理员用户不应有用户管理入口；用 /me 返回的 permissions 控制。
14. PLAN §12.2 的工时估算偏乐观（T1.5 8h、T1.7 8h、前端 16h、QA 10h）；建议按 P0 功能优先，允许把日志/统计/Docker 后置，不牺牲状态机与安全验证。

---

## 5. 关键域专项审查

### 5.1 状态机（PLAN §6.2）
- 迁移表 11 条与需求流程一致：1→2→3→4→5，驳回回 1，归档后更新回 1，2/3 锁定更新/删除 ✅。
- 存在性/权限校验：owner、当前步骤审批人、archive 权限、admin 兜底边界清楚 ✅；需补 P0-4 并发原子性与 P1-3 审批人失效。
- 建议补充用例：重复提交、驳回后原审批人再次审批旧 flow、更新升版后旧 flow 仍保持终态、归档后 update 回草稿再提交（新 flow 对应新版本）、删除已归档文件后清单刷新。
- 签名与版本绑定：flow.version 记录审批针对的版本 ✅；更新后重审批不会覆盖旧签名 ✅（按 file_id+version 查询）。

### 5.2 RBAC（PLAN §7）
- 5 角色 × 9 权限矩阵合理，资源级二层校验方向正确；admin 短路需以角色 code 判断并保证 admin 角色存在 ✅。
- 注意：权限每请求查库需做 N+1 控制（一次 join 取 roles+permissions），admin 用户禁用/角色移除立即生效。
- 注册默认 engineer（API §1.2）与"生产 ALLOW_REGISTER=false"需写入 PLAN 配置默认值。
- 越权重点抽查：草稿跨用户可见性、非审批人调用 review/approve、engineer 调用用户管理/归档、manager 更新文件、archivist 上传。

### 5.3 数据模型与索引
- 唯一约束齐备：file_number、file_versions(file_id,version)、approval_steps(flow_id,step_number)、file_number_sequences(process_code,period)、catalog_items(snapshot_id,file_number) ✅。
- 建议补：process_files(creator_id, initial_upload_time)、file_operation_logs(target_type,target_id,operation_time)、users(is_active)；软删过滤列索引评估。
- 状态统一为 int（SmallInteger）解决基线双枚举问题 ✅；MySQL/SQLite 兼容性注意 Boolean/Enum/日期类型，仅用通用类型。
- 清单条目 approved_at 缺来源（P0-2）；文件重名唯一缺规则（P0-3）。

### 5.4 安全性
- 已覆盖：JWT（PyJWT/HS256/过期/禁用）、bcrypt 直哈希（72 字节上限）、上传白名单+大小+UUID 落盘、下载鉴权+路径 resolve 校验、无静态 uploads、LIKE 转义、排序白名单、错误不泄露堆栈、SECRET_KEY 生产强制、CORS 环境化、审计日志 ✅。
- 实现时必须保证：`Path.resolve().is_relative_to(UPLOAD_DIR)`；Content-Disposition 只使用 file_number/version（不用用户可控 file_name）；上传超限删除临时文件；403/404 不泄露存在性（统一 404）。
- 建议抽查：非 PDF/可执行后缀绕过（大小写、双后缀）、版本参数注入（`../`、绝对路径）、token 算法混淆、禁用用户旧 token、密码 72 字节边界、路径分隔符 Windows 反斜杠。

### 5.5 前端范围
- 7 个功能页 + login + api.js，纯静态可实现，但建议按 P1-7 收敛为"login + 单页 tab"；不需要 iframe。
- 契约依赖：`allowed_actions`、`permissions`、分页信封、错误码中文映射；下载走 fetch+blob；401 统一跳登录；上传用 XHR 进度条。
- UI 验收：中文文案；无 npm；直接 `/ui/` 可打开；admin 与各角色按钮差异正确。

### 5.6 测试与验收
- DoD 需补：并发编号、并发审批、越权矩阵、软删全链路、路径穿越、调度纯函数、错误码一致性、真实 uvicorn 冒烟。
- 建议 qa 输出"覆盖矩阵（接口 × 用例）"与失败复现步骤；全绿以 `pytest -q` 退出码 0 为准，并附用例数/跳过数。
- 建议 Lead 在 M6 用独立 worktree 从干净状态执行：安装依赖→init_data→pytest→run.py→curl 全流程→/ui 演示，避免"本机缓存/残留数据"造成的假绿。

---

## 6. 实现阶段抽查清单（chief 使用，逐项记录证据）

1. **启动与配置**：干净 SQLite 下 `python run.py` 可起；lifespan 建表/种子；`/health` DB ok；缺 SECRET_KEY 时 prod 拒绝启动；无模块级副作用/无同步 Session 混用。
2. **认证/RBAC**：缺 token/坏 token/过期/禁用用户；五角色矩阵逐接口 403/200；越权资源级校验（改他人文件、替他人审批、删他人文件）。
3. **文件核心**：编号格式与并发唯一（10 并发）；上传白名单/大小/冷却；列表可见性过滤+total；搜索组合/日期边界/LIKE 转义；版本 major/minor/patch；2/3 状态更新删除 409。
4. **审批状态机**：全链路 + 两条驳回 + 重复审批 409 + 非法状态 409 + 非审批人 403 + 签名内容/数量/版本绑定 + 待办正确 + 并发单击。
5. **清单**：归档自动刷新、手动刷新、每日调度函数、快照历史、条目下载；旧快照/已删文件行为。
6. **下载安全**：不可见文件 404、路径穿越参数、版本不存在、磁盘缺失、日志记录、头注入。
7. **软删除**：列表/详情/下载/统计/清单过滤；编号不复用；admin 不可见但日志可追踪。
8. **用户管理**：自禁/最后一个 admin 保护、角色分配、禁用后旧 token。
9. **日志/统计**：全量日志仅 admin；筛选分页；统计数字与 DB 一致。
10. **代码质量**：无 TODO/占位；异常结构统一；无裸 commit 散落；无 N+1；中文注释/文案；requirements 与 venv 一致；README 一键启动可照做。
11. **前端**：登录/401/角色按钮/上传进度/审批弹窗/清单刷新与下载/错误提示；浏览器实际操作截图或 DOM 验证。
12. **测试有效性**：拒绝只测 happy path；抽查断言是否真的验证数据变化；运行 `pytest -q` 与冒烟。

---

## 7. 对 Lead 的请求（按优先级）

1. **今日冻结前**：转发 P0-1/P0-2/P0-3 给 PM，要求 30 分钟内修订 API.md/PLAN.md 并回执；P0-4 补入 T1.7 验收。
2. **P1 决策**：P1-2（reject 权限）、P1-4（编制人语义）、P1-5（工序分工）、P1-6（时间口径）、P1-7（前端形态）需 Lead 明确取舍并回写 PLAN/API；P1-8（requirements-dev 单一 owner）请直接指派。
3. **实现阶段**：要求 backend/frontend/qa 在提交验收前各自给出可复现命令与结果；chief 将在 M2/M3/M4/M5 各抽查一次并更新本文件，P0 不清零不出交付结论。

---

## 8. 决策闭环（Lead 2026-11-11 10:35 决策）

| 原编号 | 决策 | 状态 / chief 复核意见 |
| --- | --- | --- |
| P0-1 | 明文口令清理，改占位符 + `SEED_PASSWORD` 注入 | 待 PM 修订 API.md/PLAN.md；修订后复核 |
| P0-2 | 字段统一落 approval_steps / file_signatures / file_operation_logs；catalog_items 不存 approved_at，由 archived_at 派生 | **需修正派生源**：API §3.0/§5.0 要求 CatalogItem 返回 `approved_at`；状态 4（已批准未归档）没有 archived_at，仅用 archived_at 派生会返回 null/错误值。应使用批准通过时间（approval_steps step_number=2 的 approval_time，或 process_files.approved_at 在批准时写入）。要求 backend 明确并加用例：状态 4 文件进入清单时 approved_at 非空且等于批准时间 |
| P0-3 | 同 process_code 下未删除文件名唯一，409 FILE_NAME_DUPLICATED，软删可复用 | 待 PLAN/API 对齐；实现需说明应用层查重的并发兜底（无部分唯一索引），QA 覆盖改名/升版/软删后新上传 |
| P0-4 | 审批条件更新 + 幂等，重复 409 APPROVAL_ALREADY_DONE | **待验证**：当前 `crud/approval.py` 的 submit/review/approve 仍是"读-内存改-写"，无原子条件更新（见 IR-01），修复后复验 |
| P1-2 | reject 权限单独校验 | 待 backend 实现并加 403 用例 |
| P1-3/P1-5 | 改派、工序分工列入 out-of-scope | 接受。残余风险：审批人禁用后文件会卡单（改派不做）；建议最小兜底——提交时校验 reviewer/approver 启用（已有），审核通过时若 planned approver 已禁用则自动分配其他活跃 approver（见 IR-03），并写入交付说明 |
| P1-6 | 时间统一 UTC naive | 已落地：`utils/time.py` 全部 naive UTC 存储 + `iso()` 补 +00:00，日期区间按业务时区换算，符合 API §0.1 |
| P1-7 | 前端单页 tab（不用 iframe） | 待 frontend 按此实现，抽查 web/ |

---

## 9. 实现评审记录（滚动，基于实际代码与运行结果）

> 阶段：backend 异步化/模型/工具层已落地（10:18-10:30），routers/files.py、main.py、init_data.py、web/、tests/ 尚在编写。以下为已读代码发现的问题，编号 IR-xx，修复后逐项复验。

### 9.1 已确认的改进（基线 P0 已实质修复）

- 异步全链路：`database.py`（async engine/async_sessionmaker/aiosqlite 默认）、`crud/*`、`dependencies/*` 全部 async，无同步 Session 混用；get_db 异常回滚。
- 状态统一 int：`models/enums.py`（IntEnum + 中文标签）；模型 SmallInteger；schema 已重构。
- 模型补全：`approved_at/archived_at/deleted_at/planned_approver_id/result/file_hash/user_agent`；唯一约束齐全。
- 安全：bcrypt 直哈希（cost 12、72 字节校验）、PyJWT（exp/iat/uid/sub、过期/非法区分）、上传扩展名白名单 + 分块写 + 大小限制 + SHA-256 + UUID 落盘 + 失败清理、`resolve_storage_path` 用 resolve+relative_to 防穿越、下载头 RFC5987、无 uploads 静态挂载。
- 时间：UTC naive 存储 + ISO8601 序列化 + 业务时区日期区间换算；调度 next_run_at 纯函数。
- 序列化层 `utils/serializers.py` 基本对齐 API 字段；enums 提供中文标签映射。

### 9.2 新发现问题（按严重度）

| 编号 | 等级 | 位置 | 问题 | 要求 |
| --- | --- | --- | --- | --- |
| IR-01 | **P0（open）** | crud/approval.py submit_for_review/review_file/approve_file；routers/files.py 待核 | 状态迁移是"读-内存校验-写"，无原子条件更新；并发/双击可双签名、双推进或重复创建 flow。P0-4 决策要求未落地 | 改为条件更新（`UPDATE approval_steps SET approval_status=... WHERE id=? AND approval_status=0` 校验 rowcount；文件状态/flow 同事务条件更新），rowcount=0 → 409 APPROVAL_ALREADY_DONE；提交审核防重复需条件更新 file_status=1→2；qa 并发用例复验 |
| IR-02 | P1（open） | crud/catalog.py refresh_catalog 同秒复用 | 同秒快照复用会返回旧快照：① 同一秒内第二个文件归档，响应 snapshot 不含该文件；② 手动刷新撞上归档自动快照，返回 refresh_type=auto/operator=null，与 API §5.2 不符 | 归档触发与手动刷新不得复用不同来源快照：至少按 (refresh_type, operator_id) 匹配，或快照号加毫秒/序号后缀并始终新建；补用例 |
| IR-03 | P1（open） | crud/approval.py review_file L~230 | 审核通过时 `planned_approver_id` 对应用户若已被禁用，直接分配给禁用用户（get_user_by_id 不校验 is_active）→ 文件卡在待批准无人可批 | 若 planned approver 不存在/禁用，回退 `find_earliest_user_with_permission("approve")`，找不到再 409 NO_ELIGIBLE_APPROVER；补用例 |
| IR-04 | P1（open） | config.py ALLOW_REGISTER=True | 生产 ENV=prod 时仍默认开放自助注册，与 API §1.2 "生产默认 false" 矛盾，存在任意人注册算工时风险 | `ALLOW_REGISTER` 默认按 ENV 推导（prod=false）或在启动时 prod 且未显式配置则拒绝/告警；.env.example 注明 |
| IR-05 | P2 | crud/file.py search_files | LIKE 未转义 `% _`，API/PLAN 要求转义；用户输入 `%` 会扩大匹配 | 增加 escape 辅助并补边界用例 |
| IR-06 | P2 | models/catalog.py CatalogItem | 只有普通 Index(snapshot_id,file_number)，无 UniqueConstraint，与 PLAN §5.2 "快照内编号唯一" 不符 | 加 UniqueConstraint 或修订 PLAN（全局 file_number 已唯一，实际冲突概率低） |
| IR-07 | P2 | docs/API.md §3.0 示例 | 示例 completed flow（status=2）仍给 current_approver 非 null，backend 实现返回 null；文档示例自相矛盾 | PM 修示例；前端以字段语义为准 |
| IR-08 | P2 | config.py PROCESS_CODE_MAP | 配置了工序名→代码映射但 `normalize_process_code` 完全忽略（固定 GEN），死配置易误导 | 删除该配置或实现映射（需与 API 契约一致，不能两套规则） |
| IR-09 | P2 | utils/file_upload.py | 未拒绝 0 字节空文件；允许上传空内容后版本/下载语义异常 | 上传后 total==0 → 400 FILE_EMPTY（新增错误码需 PM 同步 API）或明确允许 |
| IR-10 | P2 | utils/pagination.py | `int(page)` 对非法字符串会 ValueError→500；当前路由 Query(int) 已挡，但工具函数应防御 | 捕获 ValueError 转 422 VALIDATION_ERROR |
| IR-11 | P1（待核） | crud/file.py find_duplicate_name | 应用层查重无并发兜底；与 P0-3 决策（应用层唯一）一致但需说明 | 路由层在同一事务内查重+创建；QA 覆盖并发同名上传（结果允许一个成功一个 409） |
| IR-12 | 待核 | routers/files.py / main.py | 事务边界（路由单次 commit、归档+快照同事务）、lifespan init_db/种子/调度启停尚未看到代码 | 代码出来后逐项验证 |
| IR-13 | 待核 | 全局 | OpenAPI 与 API.md 字段一致性、错误响应结构、路由前缀/trailing slash | 启动后用 /openapi.json 与真实请求对照 |

### 9.3 下一步抽查计划

1. routers/files.py + main.py + init_data.py 落地后：跑 `python -c "import main"`、启动 uvicorn、`/health`、`/openapi.json`。
2. 用 SQLite 跑完整 curl 全链路（登录→上传→提交→审核→批准→归档→清单→下载）。
3. 核 P0-4 修复（并发双击/条件更新）与 IR-01/02/03/04。
4. 抽查 web/ 与 tests/；执行 pytest；核对覆盖率与断言质量。

---

## 10. 变更记录

| 时间 | 内容 | 评审人 |
| --- | --- | --- |
| 2026-11-11 10:25 | 计划与契约首轮评审（P0×4、P1×15、P2×14），结论：有条件通过 | chief |
| 2026-11-11 10:38 | 记录 Lead 决策闭环；追加实现阶段首轮评审（IR-01~IR-13），P0-4 尚未落地 | chief |

---

## 11. 终验收（Lead 兼总负责人，2026-11-11 11:05）

> 自本节点起，总负责人（chief）职责并入 Lead（用户决定），本节由 Lead 独立复验并回填状态。

### 11.1 独立复验证据（Lead 亲自执行，非引用他人结论）

| 项 | 命令 / 方式 | 结果 |
| --- | --- | --- |
| 应用导入 | `python -c "import main"` | 通过（lifespan 无 import 副作用） |
| 自动化测试 | `python -m pytest -q` | **168 passed, 1 deselected（smoke），118.52s** |
| 进程级冒烟 | `python tests/smoke/run_smoke.py` | **PASS**：真实 uvicorn + SQLite 随机端口，5 角色登录→上传→提交审核→组长审核→主管批准→资料员归档→清单→下载校验→手动刷新→统计→审计日志 |
| 路由契约 | `app.openapi()` vs API.md §11 | 37 条完全一致（PM 复核） |
| 忽略规则 | `git check-ignore .env data uploads` | 均被忽略，无敏感/运行产物入库 |
| 文档口令 | docs grep 真实口令 | 0 命中（v1.0.3 全部占位符） |
| 前端 | `/ui/` 挂载 + 静态资源 + JS 语法 | 见 §11.6（frontend 联调结论） |

### 11.2 P0 闭环状态

| 编号 | 决策 | 终验结论 |
| --- | --- | --- |
| P0-1 | 明文口令清理 + SEED_PASSWORD 注入 | ✅ 已闭环：API.md v1.0.3 全占位符，PLAN §5.4 收紧；复核通过 |
| P0-2 | 字段溯源（approval_steps / file_signatures / operation_logs；approved_at 来自 process_files.approved_at，回退 archived_at） | ✅ 已闭环：模型与实现一致；QA 用例覆盖 approved_at 语义 |
| P0-3 | 同 process_code 下未删除文件名唯一（归一化 name_key）+ 软删可复用 + 并发兜底 | ✅ 已闭环：name_key 唯一索引 + 应用层校验；QA 覆盖并发同名/改名/软删复用 |
| P0-4 | 审批条件更新 + 单事务 + 重复 409 APPROVAL_ALREADY_DONE | ✅ 已闭环：crud/approval.py 条件 UPDATE + rowcount 校验；并发用例通过 |

### 11.3 IR 闭环状态

| 编号 | 等级 | 状态与证据 |
| --- | --- | --- |
| IR-01 | P0 | ✅ Closed：submit/review/approve/archive 均使用条件 UPDATE + rowcount=0→409；单事务；QA 并发用例（同一审批并发仅一次生效）通过 |
| IR-02 | P1 | ✅ Closed：`_is_reusable` 按 (refresh_type, operator_id) 复用；快照号同秒冲突加唯一后缀；QA 用例覆盖 |
| IR-03 | P1 | ✅ Closed：审核通过时 planned approver 不存在/禁用则回退 `find_earliest_user_with_permission("approve")`，找不到 409 NO_ELIGIBLE_APPROVER；QA 覆盖 |
| IR-04 | P1 | ✅ Closed：ENV=prod 强制 ALLOW_REGISTER=false 并告警；config 默认 false |
| IR-05 | P2 | ✅ Closed：`like_contains` 统一转义 `% _` 且 LIKE 带 escape |
| IR-06 | P2 | ✅ Closed：`UniqueConstraint("snapshot_id","file_number")` |
| IR-07 | P2 | ✅ Closed：API 完成态 current_approver 示例改 null（v1.0.3） |
| IR-08 | P2 | ✅ Closed：移除死配置 PROCESS_CODE_MAP，编号固定使用传入/默认工序代码 |
| IR-09 | P2 | ✅ Closed：0 字节上传 400 FILE_EMPTY，QA 用例覆盖 |
| IR-10 | P2 | ✅ Closed：分页 `_safe_int` 防御非法输入，钳制 1-100 |
| IR-11 | P1 | ✅ Closed：应用层查重 + name_key 唯一索引兜底 + 并发同名用例 |
| IR-12 | 待核 | ✅ Closed：路由单次 commit；归档+快照同事务；lifespan init_db/幂等种子/调度启停抽查通过 |
| IR-13 | 待核 | ✅ Closed：OpenAPI 37 路由一致；真实请求错误体/分页/前缀一致；冒烟覆盖 |

### 11.4 残余风险（已评估，不阻断本次交付）

1. Docker 构建与 MySQL 运行路径本机未实测（无 Docker 服务/MySQL 实例）；docker-compose 已提供，建议部署前在目标环境跑一次冒烟。
2. 每日 0 点真实定时触发未等待（纯函数单测 + ENABLE_SCHEDULER=false 冒烟覆盖）。
3. 上传冷却为进程内字典，多 worker 不共享（契约已声明单实例；生产建议网关限流）。
4. GitHub Actions CI 未在 GitHub 实跑（本机 github HTTPS 受限），本地等价命令已通过。
5. 测试 bcrypt cost=4 加速（算法同生产 cost=12，仅性能差异）。

### 11.5 交付结论

**通过，可交付。** 阻断项（P0×4、IR-01）清零；168 项自动化用例全绿 + 进程级冒烟 PASS；建议提交用户评审，确认后推送 `dhs_bot` 并创建 PR。

### 11.6 前端联调结论

Lead 独立联调（真实 uvicorn + SQLite，port 8765）：
- `/` → 302；`/ui/` → 200（6789B）；`/ui/app.html` → 200；`/ui/js/api.js` → 200（22566B）；`/health` → 200。
- `node --check` 全部 16 个 web/js 文件语法通过。
- JSON 登录 `POST /api/auth/login`（engineer01）→ 200 + Bearer token；种子 5 账号创建正常。
- 限制：本环境无浏览器，未做视觉/交互自动化验证；前端由 frontend 自测核心流程，建议用户评审时浏览器打开 `/ui/` 实测。

