# 工艺文件管理系统 发布说明（v2.0.0）

> 依据《工艺文件管理系统.md》重构，对应分支 `dhs_bot` / PR #3。详细设计与契约见 `docs/PLAN.md`、`docs/API.md`，评审结论见 `docs/REVIEW.md`。

## 1. 版本亮点

- **可运行**：修复原工程"异步数据库 + 同步调用"的阻断性问题，`uvicorn main:app` 可直接启动（dev 默认 SQLite 零配置）。
- **完整闭环**：上传 → 组长审核 → 主管批准 → 签名留痕 → 资料员归档 → 自动/手动刷新文件清单 → 检索 → 审计日志。
- **权限体系**：RBAC 5 角色（admin/engineer/leader/manager/archivist）× 9 权限，含本人/当前审批人的资源级校验。
- **文件能力**：编号 `CODE-YYYYMM-NNNN`、版本 `Vx.y.z`、重名归一化、软删除、版本历史与受控下载（防路径穿越）。
- **清单**：快照+条目两步存储；归档自动刷新、手动刷新、每日 0 点调度（`CATALOG_TZ`）。
- **检索/审计/统计**：文件名/编号/编制人/工序/状态/业务日日期 + 统一分页；操作日志；概览统计。
- **Web 界面**：`web/` 纯静态管理界面，挂载 `/ui`，`/` 重定向；无 npm 构建链。
- **质量**：168 项自动化用例（pytest + ASGITransport + SQLite）+ 进程级冒烟 + GitHub Actions CI。

## 2. 快速开始（开发环境）

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows；Linux/macOS 用 .venv/bin/pip
cp .env.example .env                               # 按需填写 SEED_PASSWORD（演示账号口令）
python run.py                                      # 打开 http://127.0.0.1:8000/ui/
```

演示账号（仅 `ENV=dev` 或 `SEED_DEMO_USERS=1` 时创建）：admin / engineer01 / leader01 / manager01 / archivist01，口令来自 `SEED_PASSWORD`。生产环境必须设置 `SECRET_KEY` 且关闭演示种子。

## 3. 生产部署

```bash
# 方式一：Docker Compose（应用 + MySQL 8）
SECRET_KEY=<至少32位随机串> docker compose up --build -d

# 方式二：已有 MySQL
# .env 中设置 DATABASE_URL=mysql+aiomysql://user:pass@host:3306/process_file_system?charset=utf8mb4
```

注意：
- 多 worker 部署时需 `ENABLE_SCHEDULER=false`，否则每日清单任务会重复执行（当前为进程内单实例调度）。
- 上传限流/冷却为进程内实现，多实例场景建议在网关层限流。

## 4. 升级与兼容

- 本次无生产存量数据；采用 `create_all` + 幂等种子建表，**未引入 Alembic**。
- 若沿用旧开发库（`data/processms.db`），请删除重建或手工 DDL 补齐新增列/索引（如 `process_files.name_key`）。
- 接口保留 `/api` 前缀；文件状态由原双枚举统一为 int（0 删除 / 1 草稿 / 2 待审核 / 3 待批准 / 4 已批准 / 5 已归档），响应附带中文文案。

## 5. 验证

```bash
python -m pytest -q                     # 168 passed, 1 deselected
python tests/smoke/run_smoke.py         # 进程级冒烟：PASS
```

## 6. 已知限制

- Docker 构建与 MySQL 真实链路未在本机实测（无 Docker/MySQL 实例），部署前请在目标环境复核。
- 每日 0 点真实定时触发未等待（由纯函数单测覆盖）。
- GitHub Actions 已配置；本地等价命令已通过。
- 范围外：PDF/Office 转换、通知、单用户互踢、分片上传、流程可视化配置、审批人自动改派、工序分工、编制人/上传人分离、CSV 导出、Alembic。
