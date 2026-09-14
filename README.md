# FastAPI Plus

轻量、模块化的 FastAPI 后端脚手架。复制或克隆项目后即可开始业务开发，应用代码、配置和迁移保留在项目中，便于理解、修改和替换。

默认使用 SQLite 和本地文件存储，无需额外服务。内置用户管理、JWT 认证、文件上传下载、数据库迁移、结构化日志和项目 CLI；MySQL、PostgreSQL、OSS、COS、Redis、Celery 按需启用。

技术栈：Python ≥ 3.11、FastAPI、Pydantic Settings、SQLAlchemy async、Alembic、structlog、Typer。依赖由 `uv.lock` 锁定，Ruff、Pyright、Pytest 用于业务开发质量检查。

## 代码结构

```text
.
├── app/
│   ├── main.py                    # Web 入口
│   ├── bootstrap/                 # 显式装配与生命周期
│   │   ├── application.py         # create_app 应用工厂
│   │   ├── lifespan.py            # 创建和释放应用资源
│   │   ├── routers.py             # 业务路由与 /health
│   │   ├── middleware.py          # 请求上下文、CORS、安全异常边界
│   │   ├── exceptions.py          # 注册异常处理器
│   │   ├── providers.py           # 装配认证及存储能力
│   │   ├── cli.py                 # CLI 资源与错误处理
│   │   └── worker.py              # 独立 Celery Worker 入口
│   ├── core/
│   │   ├── config/                # 按能力分组的类型化配置
│   │   ├── exceptions/            # 错误描述符与统一异常响应
│   │   ├── logging/               # 控制台、文件日志、请求 ID、脱敏
│   │   └── security/              # 密码哈希、JWT、权限策略入口
│   ├── common/                    # 通用响应与分页结构
│   ├── database/                  # Base、引擎、Session、最小 Repository
│   │   └── metadata.py            # Alembic 显式模型导入入口
│   ├── providers/                 # 存储和令牌撤销契约
│   ├── infrastructure/            # 契约实现与外部资源集成
│   │   ├── storage/               # Local、Aliyun OSS、Tencent COS
│   │   ├── redis/                 # 可选异步 Redis 客户端
│   │   └── celery/                # 任务配置、基类、信号、异步桥接
│   ├── modules/                   # 业务按模块组织
│   │   ├── auth/                  # 登录、刷新、退出、当前用户
│   │   ├── user/                  # 用户 CRUD，完整模块参考
│   │   └── file/                  # 上传、元数据、授权下载、删除
│   └── cli/                       # fastplus 命令
├── alembic/                       # 迁移环境、模板及版本，须随项目保留
├── docs/                          # 留给业务项目文档
├── tests/                         # 留给业务项目测试
├── .env.example                   # 配置示例，无真实秘密
├── .gitattributes                 # Python 文件使用 LF 换行
├── .gitignore
├── AGENTS.md                      # AI 开发导航与操作约定
├── alembic.ini
├── pyproject.toml
├── uv.lock
└── LICENSE
```

运行时的 `data/`（数据库、文件）和 `logs/`（可选日志）不进入版本控制。`tests/` 包含测试基建，按实际业务继续添加用例。

## 安装与启动

安装 Python ≥ 3.11 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，复制或克隆完整项目，在项目根目录执行：

```bash
uv sync --locked
```

按需将 `.env.example` 复制为 `.env`，修改项目名称、数据库和日志等配置。PowerShell 使用 `Copy-Item .env.example .env`，Linux/macOS 使用 `cp .env.example .env`；已有 `.env` 时直接编辑。

首次初始化需创建数据目录，再显式迁移和创建管理员：

```bash
uv run python -c "from pathlib import Path; Path('data/storage').mkdir(parents=True, exist_ok=True)"
uv run fastplus db upgrade
uv run fastplus create-superuser
uv run fastplus doctor
uv run uvicorn app.main:app --reload
```

管理员用户名、可选邮箱及密码由终端交互输入，密码隐藏并二次确认。没有默认账号、默认密码或自助注册接口。后续启动只需运行 Uvicorn，新增迁移时再执行升级。

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:8000/health` | 存活检查，返回 `{"status":"ok"}` |
| `http://127.0.0.1:8000/health/ready` | 数据库与已启用 Redis 就绪检查，失败返回 503 |
| `http://127.0.0.1:8000/docs` | Swagger UI，可直接调试接口 |
| `http://127.0.0.1:8000/redoc` | ReDoc 接口文档 |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI 定义 |

这些 HTTP 文档入口由 FastAPI 生成，与仓库的 `docs/` 目录无关。

## 配置

配置入口为 [app/core/config/settings.py](app/core/config/settings.py)。优先级是：显式构造参数 > 环境变量 > 当前工作目录的 UTF-8 `.env` > 默认值。配置加载后不可变，进程内缓存；修改配置需重启。未知 `.env` 字段会报错。

| 环境变量 | 默认值或说明 |
| --- | --- |
| `ENVIRONMENT` | `development`，可选 `testing`、`production` |
| `DEBUG` | `false`，生产禁止开启 |
| `APP_TITLE` | `FastAPI Plus`，接口文档标题 |
| `APP_SUMMARY` / `APP_DESCRIPTION` | 空，接口文档简介与详细说明 |
| `OPENAPI_ENABLED` | `true`，控制 Swagger、ReDoc 和 OpenAPI 入口 |
| `CORS_ALLOW_ORIGINS` | `[]`，跨域来源 JSON 数组，空数组关闭 CORS |
| `ALLOWED_HOSTS` | `[]`，空数组关闭 Host 校验；启用时填写主机名，可用 `*.example.com` |
| `READINESS_TIMEOUT` | `3` 秒，readiness 检查总超时 |
| `METRICS_ENABLED` | `false`，安装 `metrics` extra 后可启用 `/metrics` |
| `DATABASE` | `sqlite`，可选 `postgresql`、`mysql` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `5` / `10`，PostgreSQL/MySQL 每进程常驻池容量与额外连接上限 |
| `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_RECYCLE` | `30` / `1800` 秒，借连接等待超时与复用前回收年龄；回收可设 `-1` 关闭 |
| `JWT_SECRET` | 开发未设置时生成实例级临时密钥；生产必须设置至少 32 字节随机秘密 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`，范围 1–1440 分钟 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7`，范围 1–365 天 |
| `STORAGE_BACKEND` | `local`，可选 `oss`、`cos` |
| `STORAGE_LOCAL_ROOT` | `data/storage` |
| `FILE_MAX_SIZE` | `10485760` 字节，即 10 MiB |
| `REQUEST_MAX_BODY_SIZE` | `11534336` 字节，即 11 MiB，整个请求体上限，须大于文件上限以容纳 multipart 开销 |
| `LOGIN_RATE_LIMIT_ENABLED` | `false`；启用时必须同时配置 Redis |
| `LOGIN_RATE_LIMIT_CAPACITY` / `LOGIN_RATE_LIMIT_PERIOD` | `5` 次 / `60` 秒，按客户端 IP 的令牌桶容量和补充周期 |
| `LOGIN_RATE_LIMIT_PREFIX` | `fastplus:login`，同一应用多实例共用，不同应用使用不同前缀 |
| `LOG_LEVEL` | `INFO`，支持 DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `LOG_FORMAT` | 未设置时开发/测试为 `console`，生产为 `json`；仅控制控制台格式 |
| `LOG_FILE_PATH` | 未设置时仅输出控制台；指定文件路径后同时落盘 |
| `LOG_FILE_MAX_BYTES` | `10485760`，单个日志文件轮转阈值，必须为正整数 |
| `LOG_FILE_BACKUP_COUNT` | `5`，轮转备份数量，至少为 1 |
| `REDIS_ENABLED` / `CELERY_ENABLED` | `false`，连接配置见下文 |

所有相对路径均相对进程工作目录，Web、CLI 和 Worker 应在项目根目录启动。开发也建议配置固定随机 `JWT_SECRET`，否则重启会使旧令牌失效；多个进程必须使用相同密钥。

前端跨域接入示例：

```dotenv
CORS_ALLOW_ORIGINS=["http://localhost:5173","https://frontend.example.com"]
```

来源由协议、主机、端口组成，不带末尾斜线，不接受通配符。认证使用 Bearer 请求头，默认不启用跨域 Cookie。允许的方法和请求头在 [bootstrap/middleware.py](app/bootstrap/middleware.py) 显式维护；默认包含 GET/HEAD/POST/PATCH/DELETE/OPTIONS，以及 Authorization、Content-Type、X-Request-ID。浏览器可读取 X-Request-ID 和 Content-Disposition。CORS 不替代鉴权，云下载重定向后的跨域规则需在目标桶配置。

## 日志与排障

日志统一由 structlog 和标准 logging 输出到 stderr。需要本地留存时，在 `.env` 增加：

```dotenv
LOG_FILE_PATH=logs/app.log
LOG_FILE_MAX_BYTES=10485760
LOG_FILE_BACKUP_COUNT=5
```

日志目录自动创建。文件使用 UTF-8 逐行 JSON，中文直接可读；达到大小阈值时轮转为 `app.log.1` 至 `app.log.5`，旧备份自动淘汰。控制台与文件使用相同级别、请求上下文和脱敏处理，重复初始化不会增加重复输出。

本地轮转适用于**单进程独占文件**。Web、CLI 和 solo Worker 同时运行时应配置各自不同路径；Uvicorn 多 Worker、Celery prefork 等多进程部署应取消 `LOG_FILE_PATH` 配置，由进程管理器或日志收集服务接管 stderr 及轮转。不要让多个进程共写同一轮转文件。

每个 HTTP 响应包含 `X-Request-ID`。排障时从响应中取得该值，再检索日志：

```powershell
# PowerShell：包含当前文件及轮转备份
Select-String -Path logs/app.log* -Pattern '实际的请求ID' -SimpleMatch
Get-Content -Encoding UTF8 logs/app.log -Tail 50 -Wait
```

```bash
# Linux/macOS
grep -F '实际的请求ID' logs/app.log*
tail -f logs/app.log
```

`request.completed` 包含请求方法、路径、状态码与 `duration_ms`；`request.failed` 提供安全异常类型和函数/行号。任务使用 `task_id`、`correlation_id` 关联，时间统一为 UTC ISO 8601。

业务直接获取 logger，保持稳定事件名，将上下文作为字段传入：

```python
import structlog

logger = structlog.get_logger(__name__)
# 放在业务提交成功后，使用实际的业务标识。
logger.info("order.created", order_id=order.id)
```

不要记录密码、Token、完整请求体、SQL 参数或签名 URL。未知异常不会输出原始异常文本和局部变量；日志脱敏是兜底，业务仍须选择安全字段。开启文件输出后需确保目录可写，日志文件不要对外公开。

`fastplus doctor` 只读检查数据库连接、迁移状态、存储目录和已启用组件，不创建数据库或修复目录；开启文件日志时，命令的日志初始化仍会创建日志目录/文件。`/health` 仅表示进程存活；`/health/ready` 在限时内通过现有连接池执行 `SELECT 1`，并检查已启用 Redis，返回 200 或不带底层错误信息的 503。它不核对迁移版本或检查云存储、Broker，也不保证后续业务成功；发布前仍需显式迁移并运行 `doctor`。SQLite 应先初始化数据库，普通应用连接会按驱动行为创建缺失文件。

## 接口使用

在 `/docs` 调用 `POST /api/v1/auth/login`，输入管理员用户名和密码。将响应的 `data.access_token` 填入 Authorize；普通 HTTP 客户端设置 `Authorization: Bearer <access_token>`。

| 模块 | 接口 |
| --- | --- |
| 认证 | `POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`POST /api/v1/auth/logout`、`GET /api/v1/auth/me` |
| 用户 | `GET/POST /api/v1/users`、`GET/PATCH/DELETE /api/v1/users/{id}` |
| 文件 | `POST /api/v1/files`、`GET/DELETE /api/v1/files/{id}`、`GET /api/v1/files/{id}/download` |

JSON 业务接口使用 `code/message/data`，同时保留真实 HTTP 状态；错误额外包含 `request_id`。输入校验为 422，未认证为 401，无权限为 403。数据库 ID 在响应中序列化为字符串，分页参数为 `page`、`size`，最大每页 100 条。

用户管理要求超级管理员，禁止自删。刷新接口接收 `{"refresh_token":"..."}`；默认令牌撤销使用 `NullTokenStore`，退出后客户端删除两类令牌，服务端旧令牌仍有效至到期。需要强制退出或刷新防重放时，按业务实现有状态策略。

文件上传使用 multipart 的 `file` 字段和可选 `visibility`（`private` / `public`），默认私有。私有元数据和下载仅所有者或超级管理员可访问；公开文件可匿名读取，删除仍需所有者或管理员权限。支持 txt/pdf/png/jpg/jpeg/bin，扩展名与 MIME 对应关系在 [FileService](app/modules/file/service.py) 中维护。

本地文件保存到 `data/storage/{private,public}`，不静态挂载。下载返回文件流，云下载返回 307 短期签名地址，均不套 JSON 响应。应用通过 Starlette 在读取过程中限制整个请求体，覆盖 multipart、无 Content-Length 和分块传输，超限返回统一 413；文件服务仍单独校验 `FILE_MAX_SIZE`。大小和 MIME 校验不等于内容扫描；应用限额也不限制并发上传总量和接入带宽，部署层仍应设置相应容量与连接限制。

公网登录应开启 `LOGIN_RATE_LIMIT_ENABLED=true`（需 Redis），或由实际接入层提供等效限流。应用限流在密码解析和 Argon2 之前执行，成功、失败和无效格式的登录尝试都消耗额度；默认允许每 IP 突发 5 次，此后每 12 秒补充 1 次。超额返回 429 和 `Retry-After`，Redis 故障或 2 秒超时返回 503，不自动放行。多 Worker/多实例必须连接同一 Redis 并使用相同前缀。该策略不持久锁定账户，不能替代针对分布式攻击的接入防护；共享出口 IP 的用户也共享额度。

限流使用 ASGI 客户端地址，不直接读取 `X-Forwarded-For`。经过代理时，Uvicorn 的 `--forwarded-allow-ips` 只能信任实际代理地址，避免伪造 IP 绕过限流；同时避免将所有用户误判为代理 IP。直连暴露时配置 `ALLOWED_HOSTS`；启用后需将探针使用的 Host 加入允许列表。Host 校验的 400 保留 Starlette 的纯文本响应，其他 JSON 业务错误仍遵守统一契约。

## 数据库与常用命令

SQLite 开箱可用。外部数据库需预先创建数据库，并安装相应驱动：

```bash
uv sync --locked --extra postgresql
# 或
uv sync --locked --extra mysql
```

PostgreSQL 使用 `DATABASE=postgresql` 和 `postgresql+asyncpg://...` 连接串；MySQL 使用 `DATABASE=mysql` 和 `mysql+asyncmy://...`，按需加 `?charset=utf8mb4`。真实凭据写入本地 `.env` 或通过部署环境注入。

| 命令 | 用途 |
| --- | --- |
| `uv run --no-sync fastplus --help` | 查看命令帮助 |
| `uv run --no-sync fastplus version` | 查看项目及运行时版本 |
| `uv run --no-sync fastplus doctor` | 只读资源诊断 |
| `uv run --no-sync fastplus db current` | 当前迁移版本 |
| `uv run --no-sync fastplus db revision -m "add orders" --autogenerate` | 根据显式导入的模型生成迁移草稿 |
| `uv run --no-sync fastplus db upgrade` | 升级至 head |
| `uv run --no-sync fastplus db downgrade -- -1` | 显式回退一个版本，可能删除数据 |
| `uv run --no-sync fastplus create-superuser` | 交互创建管理员 |

自动生成的迁移必须检查后再执行。应用启动不自动建表、迁移或初始化账号。已应用的迁移应保留，模型变化通过新增迁移表达。

表及字段附中文 `comment`，通过 `0003_add_comments` 为已有 PostgreSQL/MySQL 补齐注释。SQLite 不支持持久化表/列注释，该迁移只推进版本，不重建表；模型中的注释仍可供开发工具使用。

连接池按**进程**创建，Web 连接预算上限为 `实例数 × Worker 数 × (DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW)`，还要给 CLI、Celery、迁移、监控及其他应用预留连接。默认 4 Worker 的上限是 60，连接按需创建，不代表启动就占满 60。例如 4 Worker 配置 `3 + 2`，Web 上限为 20；按实际并发与数据库容量调整。SQLite 保留驱动默认池策略，忽略 size/overflow/timeout；CLI 和短期任务使用 NullPool 时也不传队列池参数。`POOL_TIMEOUT` 不是查询执行超时，`POOL_RECYCLE` 也不是空闲连接自动关闭时间。

## 可选存储与任务

### OSS / COS

安装 `uv sync --locked --extra oss` 或 `uv sync --locked --extra cos`，设置 `STORAGE_BACKEND=oss` 或 `cos`，并填写对应配置：

```dotenv
# OSS
STORAGE_OSS__BUCKET=your-bucket
STORAGE_OSS__REGION=cn-hangzhou
# STORAGE_OSS__ACCESS_KEY_ID=由环境注入
# STORAGE_OSS__ACCESS_KEY_SECRET=由环境注入

# COS：ACCESS_KEY_ID / ACCESS_KEY_SECRET 分别对应 SecretId / SecretKey
STORAGE_COS__BUCKET=your-bucket-appid
STORAGE_COS__REGION=ap-guangzhou
# STORAGE_COS__ACCESS_KEY_ID=由环境注入
# STORAGE_COS__ACCESS_KEY_SECRET=由环境注入
```

只填写实际启用后端的整组配置。配置即注册后端；切换默认后端后，已有文件仍按数据库中的 `backend/key` 访问，须保留历史后端配置和 SDK。桶策略须保持 private 前缀私有，public 对象使用公开 ACL；下载链接有效期为 300 秒。

文件上传先写对象再提交元数据，数据库失败时尽力删除新对象；删除操作也跨数据库与存储。两者不具备跨系统原子事务，补偿失败需根据日志核对元数据和对象。

### Redis / Celery

应用缓存客户端使用 `uv sync --locked --extra redis`，配合 `REDIS_ENABLED=true`、`REDIS_URL=redis://localhost:6379/0`。

后台任务使用 `uv sync --locked --extra celery`，配置：

```dotenv
CELERY_ENABLED=true
CELERY_BROKER_URL=redis://localhost:6379/1
# 按需保存结果；不配置时默认忽略结果
# CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

Redis 应用客户端与 Celery Broker 的开关独立。另开终端启动 Worker，数据库配置应与 Web 一致：

```bash
uv run --no-sync celery -A app.bootstrap.worker:celery_app worker --loglevel=INFO
# Windows 本地调试
uv run --no-sync celery -A app.bootstrap.worker:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
```

solo 模式不提供 prefork 的软/硬任务超时保障。Web 不会自动启动 Worker 或 Beat。
示例 `user.status` 接收已存在的正整数用户 ID，返回用户启用状态；任务包装与注册见 [user/tasks.py](app/modules/user/tasks.py)。HTTP 入口可通过 `request.app.state.celery.send_task("user.status", args=[user_id])` 发送，须先启用任务，并在业务提交后发送；不要在请求中阻塞等待结果。

任务参数和结果只用 JSON 数据，Session、ORM 或完整 Token 不进入消息。任务复用 Service，通过集中异步桥接创建独立资源；示例仅对明确的暂时性数据库故障最多重试 3 次。

多个 extra 可重复指定：`uv sync --locked --extra postgresql --extra oss --extra celery`。同步后使用 `uv run --no-sync ...` 保留已选择的安装环境。

## 二次开发

调用方向为 `Router / CLI / Task → Service → Repository / Provider → Infrastructure`。按实际业务新增模块，已有 auth/user/file 可作为参考，不要求每个模块都创建全部文件。

1. 在 `app/modules/<业务名>/` 新建 Python 包（含 `__init__.py`）。按需添加 `model.py`、`schema.py`、`repository.py`、`service.py`、`router.py`、`dependencies.py` 和 `errors.py`。
2. Model 继承 `database.base.Base`，时间字段可用 `TimestampMixin`；在 `app/database/metadata.py` 显式导入，让 Alembic 发现模型。
3. Repository 使用 SQLAlchemy 查询，负责 add/flush/refresh，不提交事务。Service 管理业务规则与 commit/rollback，返回模型或应用结果。
4. Schema 分开声明创建、更新、查询和响应字段。Router 使用 Depends 装配 Service，解析 HTTP 并返回 `ApiResponse[T]`，不写 SQL 或直接调用云 SDK。
5. 在 `app/bootstrap/routers.py` 导入并 `include_router`，默认业务前缀为 `/api/v1`。新增 HTTP 方法或请求头时同步检查 CORS 配置。
6. 在模块 `errors.py` 定义唯一的 `ErrorDescriptor(code, key, message, status_code)`，Service 抛 `BusinessException`；安全消息由中央处理器转换，不逐路由重复捕获。
7. 生成并审阅新增迁移，在专用数据库执行升级；为业务行为在 `tests/` 添加测试，业务说明放 `docs/`。

| 扩展需求 | 修改位置 |
| --- | --- |
| 新配置字段 | `app/core/config/` 对应分组，必要时在 `Settings` 组合；同步 `.env.example` |
| 新权限规则 | `app/core/security/permissions.py`，路由使用 `require_permission("资源:动作")` |
| 新存储实现 | 实现 `StorageProvider`，放入 `infrastructure/storage/`，在 `bootstrap/providers.py` 注册 |
| 服务端令牌撤销 | 实现 `TokenStore`，在 `bootstrap/providers.py` 替换默认实例 |
| 新异步任务 | 模块内编写包装与异步处理器，在 `bootstrap/worker.py` 显式注册 |
| 新 CLI 命令 | `app/cli/` 中添加，在 `app/cli/main.py` 注册，独立装配并复用 Service |
| 应用名称与版本 | 文档名称用 `APP_TITLE`；版本来自 `pyproject.toml` 安装元数据 |

更改 Python 包分发名 `fastapi-plus` 时，也要同步 Web 工厂和 CLI 中的元数据查询名称，并执行 `uv sync`。仅更改业务文档标题无需改包名。

业务开发检查：

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest
```

测试使用临时目录、独立配置和 SQLite，Redis 限流脚本使用 fakeredis + Lua 模拟器，不读取开发者 `.env` 或操作生产资源。PostgreSQL/MySQL 注释迁移验证离线 SQL；目标数据库与真实 Redis 仍需在部署环境验证。GitHub Actions 在 push / pull request 执行锁定安装、Ruff lint/format、严格 Pyright 和 Pytest。

## 部署

从完整模板部署，保留 `alembic/` 与 `alembic.ini`。安装运行依赖：

```bash
uv sync --locked --no-dev
# 按需追加 --extra postgresql / --extra mysql / --extra oss / --extra cos / --extra celery
```

通过部署环境配置 `ENVIRONMENT=production`、`DEBUG=false`、固定随机 `JWT_SECRET` 及实际资源连接。创建数据目录，备份后显式迁移，再运行 `fastplus doctor` 和业务流程验证：

```bash
uv run --no-sync fastplus db upgrade
uv run --no-sync fastplus doctor
uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000
```

首次部署另行交互创建管理员。生产不用 `--reload`；HTTPS、进程管理、访问限制、请求体上限、日志留存和备份由部署环境配置。上线前在目标数据库与实际启用的存储、Broker 上验证业务流程。数据库与文件对象需协调备份，迁移降级不能替代备份恢复。

### 多进程与就绪探针

Uvicorn 原生支持多 Worker，使用命令行配置即可，不需要在应用 Settings 中重复实现进程管理：

```bash
uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

`--workers` 与 `--reload` 互斥。每个进程会独立启动 lifespan、连接池和可选客户端，必须共享固定 `JWT_SECRET`，并取消共享 `LOG_FILE_PATH`。生产并发写入应使用 PostgreSQL/MySQL；SQLite 允许多进程访问，但写锁竞争使它不适合作为多 Worker 并发写入方案。“SQLite 绝对不能多 Worker”并不准确。

同机多 Worker 可以访问同一个 Local 目录；跨机器多实例必须使用共享存储或 OSS/COS，否则其他实例无法读取已上传文件。文件存储和数据库自身的高可用、备份仍由部署环境负责。

编排环境将 liveness 指向 `/health`，readiness 指向 `/health/ready`，探针超时应大于 `READINESS_TIMEOUT`。例如每 10 秒探测、超时 5 秒、连续失败 3 次移出流量；迁移应在发布步骤单独执行。进程数增加本身不等于高可用，还需配置滚动更新、流量摘除和优雅退出。

### 可选基础指标

```bash
uv sync --locked --extra metrics
```

配置 `METRICS_ENABLED=true` 后提供 `/metrics`（Prometheus 文本，不进入 OpenAPI），必须通过实际网络策略只允许监控系统访问。关闭时不加载指标依赖，也不暴露端点。

当前指标使用进程独立注册表：**每个被采集的地址只运行一个 Worker，通过多实例扩容并逐个采集**。不要对 `--workers 4` 的共享端口或负载均衡地址直接采集，这会随机读取单个进程，导致计数与延迟统计失真。传统同端口多 Worker 部署可关闭本功能并使用接入层指标；需要进程聚合时再按 Prometheus 官方 multiprocess 生命周期约定集成，不能仅加环境变量就视作已支持。

| 指标 | 用途 |
| --- | --- |
| `http_requests_total{method,route,status}` | 请求量和状态码；`rate(...[5m])` 得到 QPS |
| `http_request_duration_seconds_bucket` | 延迟分布，可用 `histogram_quantile` 计算 P99 |
| `db_pool_checked_out` | 当前进程借出的连接数 |
| `db_pool_size` | 常驻队列池容量，不含 overflow；内存 SQLite/无队列池时为 0 |

路由标签使用 `/users/{user_id}` 这类模板，未知路径归为 `unmatched`，不包含实际 ID、query、IP 或 Token。探针和 `/metrics` 不计入 HTTP 指标。延迟包含响应流及请求结束阶段，不等同于数据库耗时；流开始后失败仍保留已发送的状态码，排障需结合错误日志。

例如跨实例 P99：`histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))`。HTTP 5xx 比例：`sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`，无请求时分母为零，告警规则需处理低流量。抓取、保存和告警规则由实际监控平台配置；Celery 积压、数据库服务端与主机磁盘指标应由相应 exporter 提供，本项目不启动监控服务器。

### 按业务再补的能力

Beat 调度、用户缓存、存储配额、业务审计日志和更严格的密码策略按业务引入。当前认证每次查询用户，保留禁用立即生效；CLI 已复用 8–128 字符密码校验，建议管理员使用密码管理器生成的长随机密码。没有定时任务时无需预置空调度器；引入 Beat 时必须单独部署且保持单调度实例、任务幂等。CSP、HSTS 和防嵌入响应头按实际 HTTPS/前端策略配置，不为通用 API 强制套用可能破坏文档页的策略。本项目不内置 Docker、Compose 或 Nginx 配置。

## 许可证

[MIT License](LICENSE)。
