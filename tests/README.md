# 自动化测试说明（qa）

## 运行

```bash
# 全量单元/接口测试（临时 SQLite + httpx ASGITransport，无需 MySQL）
D:/dsh_workspace/.venv/Scripts/python.exe -m pytest -q

# 只跑某组
D:/dsh_workspace/.venv/Scripts/python.exe -m pytest tests/test_approval.py -q

# 进程级冒烟（真实启动 uvicorn + SQLite，跑完整业务闭环）
D:/dsh_workspace/.venv/Scripts/python.exe tests/smoke/run_smoke.py
# 或通过 pytest 包装（默认跳过）
RUN_SMOKE=1 python -m pytest tests/smoke -m smoke -q
```

依赖安装：`pip install -r requirements-dev.txt`（含 pytest/pytest-asyncio/httpx、tzdata、greenlet）。

## 测试基座

- 每个用例独立创建临时 SQLite 文件库（`sqlite+aiosqlite`），不依赖真实 MySQL；
- 不触发应用 lifespan（httpx ASGITransport 不执行 startup），夹具手动 `create_all` + 调用后端 `init_data.seed_data` 种子；
- 通过 `app.dependency_overrides[get_db]` 注入测试会话；
- 种子：5 角色 / 9 权限 / 角色权限矩阵 / 5 演示账号（密码由 `SEED_PASSWORD` 环境变量注入）+ 额外 engineer02、norole01；
- `settings.UPLOAD_DIR` 指向临时目录；`UPLOAD_COOLDOWN_SECONDS=0`（限流用例单独设为 2）；
- 认证头用签名正确的 JWT 直构，避免每用例 bcrypt 登录；仅认证用例走真实登录；
- 自动清理 `routers.files._upload_last_at` 进程内冷却状态，保证顺序无关。

## 覆盖矩阵（接口/分支要点）

| 文件 | 覆盖点 |
| --- | --- |
| test_units.py | 版本号解析/递增/校验、文件编号格式、分页钳制、调度 `next_run_at`、bcrypt、JWT 过期/非法、UTC/业务时区工具 |
| test_auth.py | 登录成功/错误口令/禁用/校验错误、me、过期/非法 token、禁用用户旧 token、改密（旧密错/同密/短密）、注册（成功/重复用户名/重复工号/开关关闭/短密） |
| test_rbac.py | 5 角色权限矩阵、engineer 无管理/审批/归档/清单权限、leader 可审核不可批准、manager 不可上传/审核、archivist 归档+刷新、admin 全通、无角色用户、越权本人文件（404 可见性）、非当前审批人 403、reject 权限分支 |
| test_users.py | 用户分页/关键字、创建（角色/重复/非法角色）、本人可读/他人 403、更新、角色整体替换、禁用后登录失败、自禁 409、最后管理员保护、角色/权限数组 |
| test_upload.py | 上传字段与编号规则（CODE-YYYYMM-NNNN、业务时区）、默认 GEN、扩展名/大小校验、同工序重名（含空白/大小写归一化、软删可复用、改名冲突）、编号递增唯一、并发上传唯一、版本格式、空文件、中文文件名、落盘存在且不含客户端文件名、限流 429 |
| test_versions.py | patch/minor/major 升版、元数据更新不变版本、审核中 409 FILE_LOCKED、已批准必须带新文件、升版回草稿、版本历史字段/排序/默认变更说明、指定版本下载、非法 version_type、草稿改工序代码 |
| test_approval.py | 上传→提交→审核→批准→归档全链路、指定审批人、审核通过生成 step2、审核/批准驳回回草稿+签名、非法状态 409、重复提交/审核、待办（review/approve/keyword/权限）、流程与签名查询、allowed_actions 随状态变化、并发审核/批准仅一次生效、完成态 current_approver=null、预分配主管禁用回退 |
| test_download.py | 下载头/内容、无 token 401、不存在/不可见草稿/已删除 404、归档全员可见、磁盘缺失 FILE_CONTENT_MISSING、路径穿越版本参数拒绝、下载日志 |
| test_search.py | keyword/编号/名称/工序/工序代码/编制人 ID/编制人姓名/状态/业务日日期区间、分页 total/pages/越界/size 钳制、非法排序 422、LIKE 转义、可见性、组合筛选、业务日上传筛选 |
| test_catalog.py | 无快照空结果、归档自动刷新、手动刷新（类型/操作人/条目数/幂等）、manual 不复用 auto、快照历史/详情/404、条目字段与 approved_at 语义、下载链接可下载、分页/筛选 |
| test_delete.py | 本人草稿软删后详情 404/列表不可见、越权 404/403、admin 可删他人草稿、审核中 409、归档文件仅 admin 可删、编号不复用、清单剔除 |
| test_logs.py | 全量日志（仅 user_manage）、操作类型/目标类型/日期筛选、分页、登录日志、单文件日志权限（他人草稿 404）、业务日筛选 |
| test_stats.py | 空系统结构、非 admin users=null、归档后状态分布/清单/最近操作、待办计数随流程变化、总数一致性 |
| test_pagination.py | 文件/清单/日志/待办/用户默认 size=10、统一分页信封 |
| smoke/run_smoke.py | 进程级：SQLite 建库+种子→uvicorn→登录 5 角色→上传→提交→审核→批准→归档→清单→下载校验→手动刷新→统计→日志，失败退出码 1 |

## 已知约定

- 日期筛选按业务时区（`CATALOG_TZ`，默认 Asia/Shanghai）解释，响应时间仍为 UTC ISO8601；
- 同秒快照复用（相同刷新方式+操作人）；清单/日志相关用例跨秒等待以生成独立快照；
- 进程级冒烟需本机可用端口与写临时目录权限；CI 无 .env 时使用测试环境变量。
