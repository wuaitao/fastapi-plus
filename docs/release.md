# M9 发布验收

M9 为 FastAPI Plus v0.1 完成测试、兼容性、文档和架构加固。
当前版本仍是 `0.1.0.dev0`；本记录不表示已打标签、发布软件包或部署生产。

全量审计后的新旧脚手架对照与增量收口见 [scaffold-review](scaffold-review.md)，
包括 CORS、OpenAPI 元数据、换行符及本轮验证；下文原审计/M9 记录保留其历史时点。

## 最终审计复验

M0–M9 全量审计、目录对齐、TokenStore 精简和安全/并发修复详见 [audit](audit.md)。
2026-09-13 最终复验：Ruff lint/format、Pyright strict 通过；Pytest 380 passed，无 skip/xfail；
综合覆盖率 95.31%，Core 98.52%、Security 100.00%、Database 92.81%。
PostgreSQL/MySQL 在线发布用例各 4 passed，真实 Redis/独立 Worker 1 passed；
干净模板 locked/no-dev 安装与真实 Uvicorn 流程通过，48 次并发认证读取和 6 个并发创建均成功。
这些检查不等于容量、故障转移或 SLA 验收；当前可靠性边界与发布待办见审计报告。

## 原 M9 验证记录

2026-09-13，在 Windows 11、Python 3.13.15 上验证；使用真实本地服务，无 Docker。
FastAPI 0.141.1、SQLAlchemy 2.0.52、Alembic 1.20.0；依赖由 `uv.lock` 固定。

| 项目 | 结果 |
| --- | --- |
| uv sync | 通过 |
| Ruff lint / format | 通过 |
| Pyright strict | 0 errors、0 warnings |
| Pytest | 369 passed，无 skip/xfail |
| coverage.py 语句与分支综合覆盖率 | 整体 95.25%；Core 98.50%；Security 100.00%；Database 92.81% |
| OpenAPI | 全部引用可解析、operationId 唯一、描述/tags、envelope、错误、Bearer 和下载契约通过 |
| 架构 | Router/Service/Repository/Provider、显式 Bootstrap、独立 CLI/Worker 边界检查通过 |
| 干净模板副本 | locked/no-dev 安装、可选包缺席、显式迁移、管理员创建、doctor、真实 Uvicorn HTTP 验证通过 |

| 数据库 | 驱动 | 空库升级 / check / 降级 / 再升级 | Repository / Auth / User / File |
| --- | --- | --- | --- |
| SQLite 3.50.4 | aiosqlite | 通过 | 通过，默认测试覆盖 |
| PostgreSQL 17.11 | asyncpg 0.31.0 | 通过 | 4 个在线发布用例通过 |
| MySQL 8.0.46 | asyncmy 0.2.14 | 通过 | 4 个在线发布用例通过 |

每种数据库执行同一个 `tests/integration/database/test_release.py`，验证真实事务与迁移，
包括 Repository 不隐式提交、Service 冲突后回滚、自动主键、UTC、分页、并发用户名/邮箱唯一约束，
管理员创建、登录/刷新/退出、401/403、公开/私有文件上传下载删除和所有者删除后的外键置空。
数据库仅含本次生成的数据；Local 使用临时目录，不连接已有业务库。

干净副本由版本控制文件和本次变更组成，不复制原虚拟环境、缓存或运行数据。
管理员输入使用新解释器中的 Typer CliRunner 验证提示/密码确认；迁移和 doctor 执行安装后的 CLI，
HTTP 请求连接独立 Uvicorn 进程。Windows 隐藏进程不能用普通 stdin 管道替代 getpass 控制台交互，
实际使用 `create-superuser` 时应在交互终端执行。

## 三数据库在线验证

普通 `uv run pytest` 默认使用临时 SQLite。单独执行发布流程：

```bash
uv run pytest tests/integration/database/test_release.py -q
```

外部数据库需先由操作者创建专用空库，例如 `fastplus_test_release`，并使用仅能操作此库的测试账号。
通过环境注入 `FASTPLUS_TEST_DATABASE_URL`；PostgreSQL 使用 `postgresql+asyncpg://...`，
MySQL 使用 `mysql+asyncmy://...`，建议指定 `?charset=utf8mb4`。
不要把密码直接写入命令、版本控制或报告，也不要用应用的 DATABASE_URL 代替此测试变量。

```bash
uv run --extra postgresql pytest tests/integration/database/test_release.py --release-database=postgresql -q
# 将 FASTPLUS_TEST_DATABASE_URL 切换到 MySQL 专用空库后执行
uv run --extra mysql pytest tests/integration/database/test_release.py --release-database=mysql -q
```

测试要求后端匹配、库名以 `fastplus_test_` 开头且没有表或视图；缺失配置和非空库均报错。
测试会创建并删除表，执行降级/再升级，完成后恢复为空库。不得连接开发或生产数据库，
不得让多个测试进程共享该库；中断后检查并重建专用测试库再运行。
驱动安装或离线 SQL 编译通过不等于在线验证通过。

本次使用本机已有的 MySQL 二进制和 [PostgreSQL 官方推荐的 Windows 二进制](https://www.postgresql.org/download/windows/)，
各自使用独立临时数据目录、随机密码、回环地址和临时端口，结束后停止进程。
这些二进制与本次启动辅助文件只用于临时验证，不是项目依赖，也不加入版本控制；
任意独立测试服务器均可运行上述命令。

## 默认安装与部署

从完整模板检出启动，遵循 [README](../README.md#启动应用)。
迁移源码和 `alembic.ini` 必须随模板保留；单独安装 wheel 不等于拥有完整模板和迁移文件。
生产安装使用 `uv sync --locked --no-dev`，需要外部能力时明确加对应 extra。

生产环境通过部署环境提供 `ENVIRONMENT=production`、`DEBUG=false` 和随机 `JWT_SECRET`（至少 32 字节），
以及实际数据库/存储配置。多个进程使用同一个秘密；不提交 `.env` 或输出配置秘密。
先备份数据库与文件对象，再显式执行 `uv run --no-sync fastplus db upgrade`，首次安装使用
`uv run --no-sync fastplus create-superuser` 交互创建管理员。创建存储根目录后运行
`uv run --no-sync fastplus doctor`，再运行 `uv run --no-sync uvicorn app.main:app`，生产不用 `--reload`。
安装后使用 `--no-sync` 保留已选 extras 和 no-dev 环境，避免运行命令时重新同步开发依赖。
HTTPS、访问控制、请求大小限制和进程管理由部署环境提供；本项目不要求 Docker 或特定反向代理。
可按需关闭 `OPENAPI_ENABLED`；健康探针只表示进程存活，不代替 doctor 和业务流程验证。

升级前检查 CHANGELOG 和迁移源码，在与目标生产版本一致的专用数据库中完成本页测试。
迁移可能删除数据，降级不是备份恢复；对生产执行 downgrade 前须评估并验证恢复方案。
数据库与存储应协调备份，尤其是文件上传补偿或删除失败后需要核对的对象与元数据。

## 安全与范围审查

- 未引入真实秘密、默认账号或默认密码；示例秘密留空，测试数据仅用于独立测试资源。
- 默认 SQLite/Local 可运行；Redis/Celery/云 SDK/外部驱动保持可选，启动不建表、不迁移、不创建管理员。
- 未引入 Docker/Kubernetes、前端代码、完整 RBAC、租户或第四个业务模块。
- 唯一新增依赖为开发组的 coverage.py（Apache-2.0）；运行时依赖不变，声明与锁文件同步。
- Repository 不 commit/rollback，Service 管理业务事务，Router 保持 HTTP 职责；Provider 不依赖 Adapter。
- 密码/Token/错误/日志脱敏、权限、私有文件路径与补偿已有行为测试；源码检查不等同于第三方渗透测试。

## 已知限制与正式发布待办

- 本次运行平台为 Windows/Python 3.13.15；Python 最低声明 3.11，Linux/macOS、其他 Python/数据库版本
  未在本次完成实机矩阵，使用这些环境发布前需重跑。MySQL 时间精度和大小写排序规则差异见 [database](database.md)。
- 默认 JWT 退出不撤销已签发令牌，旧 refresh 可重用；Redis 客户端已实现，但没有 RedisTokenStore 或刷新防重放。
- 文件数据库与对象存储不是原子事务，补偿可能失败；上传 MIME/扩展名检查不是内容扫描，框架暂存前的请求大小限制由部署层负责。
- OSS/COS 的普通测试模拟 SDK 边界，本次未使用真实云账号验证 ACL/签名；正式使用云后端前运行 [真实云验收](storage.md#云后端配置)。
- 默认任务测试含 memory Broker 非 eager Worker；最终审计已复验真实 Redis/独立 Worker，Windows solo 仍不验证 prefork 超时保障。
- LICENSE 年份已填为 2026，版权主体尚待维护者填写；完成这一项及目标环境验收后，再决定版本号、标签和正式发布。
