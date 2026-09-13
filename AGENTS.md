# FastAPI Plus：AI 开发指南

这是用于直接开发业务应用的 FastAPI 模板，应用代码属于当前项目。用户提出业务需求时，在现有模块化结构中实现；不要恢复脚手架开发阶段的路线图、审计报告或阶段测试。

先阅读 [README.md](README.md) 中的配置、使用和二开说明，再检查任务相关代码。`docs/` 和 `tests/` 初始仅含占位文件，后续只添加当前业务确需的说明和测试。

## 快速操作

在项目根目录执行，Python ≥ 3.11，使用 uv 管理 `.venv`：

```bash
uv sync --locked
uv run python -c "from pathlib import Path; Path('data/storage').mkdir(parents=True, exist_ok=True)"
uv run fastplus db upgrade
uv run fastplus create-superuser
uv run uvicorn app.main:app --reload
```

初始化数据库和管理员是显式操作，后续启动不重复创建。管理员命令需要交互终端，不预设密码。已有业务数据库的迁移与账号修改须按用户授权范围执行。

默认 SQLite + Local，Redis/Celery 关闭。按需要安装 `postgresql`、`mysql`、`oss`、`cos`、`redis`、`celery` extras；生产安装加 `--no-dev`。选好安装环境后用 `uv run --no-sync ...`，避免重新同步移除 extras 或引入开发依赖。

```bash
uv run --no-sync fastplus --help
uv run --no-sync fastplus version
uv run --no-sync fastplus doctor
uv run --no-sync fastplus db current
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
# 已有业务测试时执行；初始空目录的退出码 5 不代表通过
uv run --no-sync pytest
```

Ruff 同时负责 lint、导入排序和格式，Pyright 使用 strict。按需执行 `ruff format`。不要添加重复主工具或用 skip/xfail、放宽断言、广泛 ignore/noqa 隐藏问题。

## 代码导航

| 任务 | 入口 |
| --- | --- |
| Web 创建与资源启停 | `app/bootstrap/application.py`、`lifespan.py` |
| 新增/调整业务路由 | `app/bootstrap/routers.py`，默认 `/api/v1` |
| 中间件顺序及 CORS | `app/bootstrap/middleware.py` |
| 配置字段与来源 | `app/core/config/`，由 `settings.py` 组合 |
| 统一响应与分页 | `app/common/response.py`、`pagination.py` |
| 应用错误、HTTP 转换 | `app/core/exceptions/` |
| 日志配置与脱敏 | `app/core/logging/` |
| JWT、密码、权限策略 | `app/core/security/` |
| 当前用户与身份依赖 | `app/modules/auth/dependencies.py` |
| 数据库、Session、Repository | `app/database/` |
| Alembic 模型发现 | `app/database/metadata.py`，必须显式导入模型 |
| 完整业务模块参考 | `app/modules/user/` |
| 跨存储业务与补偿参考 | `app/modules/file/` |
| 能力契约与实现 | `app/providers/`、`app/infrastructure/` |
| 能力实例选择 | `app/bootstrap/providers.py` |
| CLI 注册与独立资源 | `app/cli/main.py`、`app/bootstrap/cli.py` |
| Worker 注册与任务资源 | `app/bootstrap/worker.py`、`app/infrastructure/celery/` |

存在 `.codegraph/` 且工具可用时优先用 CodeGraph 定位调用链和影响范围，再读取索引未覆盖的细节；没有可用索引时使用正常代码搜索，不把建索引作为开发前置条件。生成代码、配置或使用库 API 时用 Context7 核实；不可用时说明并查官方文档。

## 实现业务的方法

运行方向：`Router / CLI / Task → Service → Repository / Provider → Infrastructure`。

- **Router** 解析 HTTP、声明认证授权依赖、调用 Service、序列化 Schema。不写 SQL、业务事务或厂商 SDK 调用，不逐路由重复捕获业务异常。
- **Service** 负责业务规则、协调依赖以及 commit/rollback，返回 ORM 或应用结果。不得依赖 Request、Depends、HTTPException、JSONResponse 或具体厂商 SDK。认证与用户管理沿用现有 Service，不另写一套逻辑。
- **Repository** 使用 SQLAlchemy 查询、add/flush/refresh，永不 commit，不做 HTTP、权限或业务流程。已有最小 BaseRepository 可用，复杂查询直接放模块 Repository。
- **Provider** 是最小应用能力契约。Infrastructure 实现它，契约不反向导入 Adapter；SDK 类型和阻塞调用留在 Adapter。
- **Bootstrap** 显式选择实现并装配，不自动扫描路由或模型，不启动业务任务、建表或初始化账号。

新增模块放 `app/modules/<name>/`，必须包含 `__init__.py`。按实际需要创建 model/schema/repository/service/router/dependencies/errors，避免空壳文件。注册路由到 `bootstrap/routers.py`，模型导入到 `database/metadata.py`，数据库变更新增 Alembic 迁移：

```bash
uv run --no-sync fastplus db revision -m "describe change" --autogenerate
# 审阅生成结果后，在专用开发数据库验证
uv run --no-sync fastplus db upgrade
```

保留已有迁移，不重写已经应用的版本。数据库主键默认整数，按需在响应 Schema 中序列化为字符串。模型时间使用 `TimestampMixin` / `UTCDateTime`，写入值带时区；直接 SQL 写入需自行维护时间字段。

请求和任务各有独立 Session，入口关闭资源，Service 完成事务。身份查询使用独立短 Session，返回用户快照；不要跨请求共享 Session，或通过身份快照修改用户。阻塞密码哈希和 SDK 调用复用已有线程边界；任务复用集中异步桥接，不在每个任务内另建事件循环。

新增任务参考 `modules/user/tasks.py`，在 Worker 工厂显式注册。仅传简单 JSON 参数和结果，业务提交后再投递；数据库与 Broker 不具备原子提交。为可能重复执行的任务实现业务幂等，只重试明确的暂时性故障。

## 配置、API 与安全边界

配置只能从 `Settings` 获取，业务模块不自行读取环境变量。来源优先级为构造参数 > 环境变量 > 根目录 `.env` > 默认值。普通字段平铺，云存储嵌套变量使用双下划线。新字段加入对应配置分组，同步 `.env.example` 和必要的 README 说明。

生产必须提供至少 32 字节随机 `JWT_SECRET` 并关闭 DEBUG。开发临时密钥重启失效，多进程使用相同固定秘密。密码、Token、连接串和云密钥不得硬编码、记录或提交。

JSON 业务 API 返回 `code/message/data`，错误包含 `request_id`，保留 HTTP 状态码及自定义 422。文件、流、重定向不强制包装。模块错误用唯一数字 code、key、安全 message、status_code 描述，Service 抛应用异常。未知异常集中处理，不回显异常正文。

权限入口为 `check_permission` / `require_permission`，默认只允许超级管理员。业务需要细粒度权限时在此按授权范围扩展，不把 `is_superuser` 规则误认为已有完整 RBAC。默认 `NullTokenStore` 不撤销令牌，退出要求客户端清理，刷新不提供防重放。

CORS 默认关闭，只接受明确来源；新增方法/请求头时检查原生中间件允许列表。请求顺序为请求上下文 → 可选 CORS → 安全异常边界 → 框架与路由，预检和错误响应都应保留请求 ID。流开始后失败应中止，不能发送第二个 JSON 响应。

私有文件不得公开静态挂载，原始文件名不作路径。读取和删除必须经过 Service 授权，历史对象按记录中的 backend/key 定位。保留上传失败补偿及取消时等待线程结束的逻辑；数据库回滚无法恢复已经删除的对象。

## 日志使用

业务通过 `structlog.get_logger(__name__)` 获取 logger，使用稳定事件名和安全结构化字段，不自行注册 Handler 或使用 print。非显然逻辑附中文说明，公共操作的 docstring 应交代用途、事务或副作用，避免只复述函数名。

默认输出 stderr；`LOG_FILE_PATH` 显式启用 UTF-8 JSON 文件日志，大小与备份数由 `LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT` 控制。两种输出共用上下文与脱敏。

轮转文件必须由单进程独占，Web/CLI/solo Worker 并行运行需使用不同路径；多 Worker 或 prefork 使用 stderr 和外部收集，取消文件配置。时间保持 UTC；用响应 `X-Request-ID` 查 `request.completed` / `request.failed`，任务用 correlation_id/task_id 关联。不要为排障关闭脱敏或输出完整秘密配置。

## 变更与验证

先说明任务假设、最小修改和验证方式。保持脚手架通用性，只增加当前业务确需的能力，不为未来需求预装服务、创建复杂 IoC 或通用 CRUD 框架。用户要求的新业务不受旧里程碑范围限制。

行为修改在 `tests/` 添加对应业务测试，缺陷先复现再修复。可按 unit/integration/api 分层，目录按需创建；Repository 使用真实 SQLAlchemy，Local 使用临时文件系统，云 SDK 可在边界模拟。测试隔离 `.env`、Settings 缓存、进程日志与资源，不连接生产。

涉及模型时验证迁移，涉及 API 时检查实际响应和 OpenAPI，涉及外部服务时明确哪些做了真实验证。运行适用的 Ruff、Pyright、Pytest；没有业务测试时报告实际冒烟验证，不宣称全量测试通过。

新增依赖同步 `pyproject.toml` 和 `uv.lock`，优先标准库及已有能力，运行依赖和 dev 分开。修改包名时同步应用工厂、CLI 的元数据查询；修改版本后重新安装当前项目。

完成后审查 diff，报告行为变化、文件、真实验证结果和剩余限制。运行数据、日志、密钥、缓存、临时验证脚本不提交；业务文档和测试按需保留，README 与 AGENTS 不再承载开发阶段的过程报告。
