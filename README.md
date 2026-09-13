# FastAPI Plus

一个轻量、面向生产的 FastAPI 后端 Starter。采用 **Template-first** 产品形态：
通过克隆仓库或使用模板开始，应用代码留在项目中，便于阅读、修改和替换。

> Secure by default. Extensible by design. Minimal in core. Explicit is better than magic.

## 当前状态：M9 — Release Hardening

当前已实现应用工厂、类型化配置、集中 Lifespan、显式路由注册和 `GET /health`，
以及 structlog、请求 ID、泛型响应/分页、应用异常与全局异常处理。
M3 已加入 SQLAlchemy async、独立 Session、UTC 时间字段、最小 Repository 和 Alembic。
M4 已加入完整 User 参考模块、Argon2id 密码哈希、唯一冲突处理和 users 表迁移。
M5 已加入 JWT access/refresh、登录/刷新/退出/当前用户、Bearer 依赖及用户管理权限。
M6 已加入 StorageProvider/Registry、Local/OSS/COS、文件 API、files 迁移和失败补偿。
M7 已加入可选 Redis/Celery、独立 Worker、集中异步桥接和一个用户状态查询任务。
M8 已加入 Typer CLI：版本、只读诊断、Alembic 命令和交互创建超级管理员。
M9 补齐三数据库发布流程测试、覆盖率门槛、OpenAPI 完整性与架构边界检查，并整理发布文档。
测试覆盖配置、生命周期、Health、422/404/405/500、日志脱敏、并发上下文和 OpenAPI。
版本 `0.1.0.dev0` 表示开发中的基础仓库，并非已发布的 v0.1。

**Redis/Celery 默认关闭；用户管理接口要求超级管理员权限。**
`alembic/`、`alembic.ini` 可执行显式 users/files 迁移，不自动创建管理员；
`.env.example` 列出可选配置，默认无需创建 `.env` 或填写密钥。
开发未配置 JWT_SECRET 时使用实例级随机临时密钥，重启后旧令牌失效；生产必须配置
至少 32 字节的随机秘密。默认退出不撤销服务器令牌，客户端应删除 access/refresh。
没有默认管理员，也没有自助注册端点；使用 `uv run fastplus create-superuser` 创建管理员。
接口输入与状态码见 [API 契约](docs/api.md)，实际兼容性和待发布事项见 [发布验收](docs/release.md)。

## 启动应用

安装 Python >= 3.11 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，
克隆仓库或使用模板后，在仓库根目录执行：

```bash
uv sync
uv run fastplus db upgrade
uv run fastplus create-superuser
uv run uvicorn app.main:app --reload
```

管理员用户名、可选邮箱和密码由 CLI 交互输入；密码隐藏并要求确认。
迁移和管理员创建均须显式执行，重复启动服务器不需要重复创建账号。

访问 `http://127.0.0.1:8000/health`，返回 `{"status":"ok"}`。
交互文档位于 `/docs`、`/redoc`，OpenAPI 位于 `/openapi.json`。
`OPENAPI_ENABLED=false` 可独立关闭这些文档入口。
`LOG_FORMAT=json` 可切换 JSON 日志；未指定时开发/测试使用 console，生产使用 JSON。
所有 HTTP 响应携带 `X-Request-ID`；Health 响应体保持原格式。
配置来源、变量名及当前校验边界见 [configuration](docs/configuration.md)。
数据库默认 SQLite，支持可选安装 PostgreSQL/MySQL 驱动；配置、Session 用法和
显式 Alembic 命令见 [database](docs/database.md)。应用启动不连接数据库、不建表或迁移。

文件默认写入 `data/storage/private`，上传需登录；私有文件仅所有者或超级管理员可读写。
公开文件支持匿名下载，所有文件删除仍需所有者或超级管理员权限。
默认最大 10 MiB，支持 txt/pdf/png/jpg/jpeg/bin；接口、类型约束和云配置见 [storage](docs/storage.md)。
默认 `uv sync` 不安装云 SDK；按需使用 `uv sync --extra oss` 或 `uv sync --extra cos`。

默认应用不要求 Redis 服务或 Worker。部署使用 `uv sync --no-dev` 时不安装 Redis/Celery，
按需加 `--extra redis` 或 `--extra celery`；开发组安装任务测试所需的 Celery/Redis 和类型桩。
开关、连接配置、独立 Worker 启动和唯一示例任务见 [Celery 与异步任务](docs/celery.md)。

## 验证首次使用

1. 在 `/docs` 执行 `POST /api/v1/auth/login`，使用刚创建的用户名和密码。
2. 将返回的 `data.access_token` 填入 Authorize，调用 `/api/v1/auth/me` 和用户管理接口。
3. 在 `POST /api/v1/files` 上传 txt 文件，默认 private；根据返回的字符串 ID 查询、下载和删除。
4. 使用 `POST /api/v1/auth/refresh` 的 JSON 请求体刷新令牌；退出后客户端删除两个令牌。

本地文件首次上传会创建存储目录。若需上传前运行 `fastplus doctor`，先显式创建
`data/storage`（PowerShell：`New-Item -ItemType Directory -Force data/storage`；POSIX：`mkdir -p data/storage`）。
`/health` 只检查进程存活；`uv run fastplus doctor` 检查连接、迁移状态和存储条件。
部署配置、备份、升级步骤和已知限制见 [发布验收](docs/release.md)。

## 核心理念与架构

**Lightweight / Explicit / Modular / Replaceable / Predictable**

- 核心依赖少，默认使用 SQLite 和 Local 文件系统。
- 按业务模块组织代码，显式注册路由和装配依赖。
- 使用成熟框架原生能力，只抽象稳定的应用能力。
- 可选基础设施未安装且未启用时，不影响基础应用。

当前 Auth/User/File、CLI 与 Worker 遵循以下调用方向：

```text
HTTP Router / CLI / Celery Task
              ↓
           Service
              ↓
     Repository / Provider
              ↓
        Infrastructure
```

Service 管理业务与事务；Repository 管理数据库访问；
Infrastructure 实现 Provider 契约。详见 [架构](docs/architecture.md)。
M0–M9 的目录已按 [设计代码树](docs/Project%20Structure.md) 归位：Bootstrap 显式装配，
配置、异常和日志按职责拆分，TokenStore 契约与默认空实现合放，测试按层及业务模块组织。

## v0.1 功能范围

- FastAPI 应用工厂、Pydantic 配置、structlog、请求 ID、统一响应与异常。
- SQLAlchemy 2.x async、Alembic；默认 SQLite，支持 MySQL 和 PostgreSQL。
- `auth`、`user`、`file` 三个参考模块；Argon2id 与 JWT access/refresh token。
- 默认 Local 存储，支持 Aliyun OSS、Tencent COS。
- Redis、Celery 可选且默认关闭；项目 CLI、测试和文档。

无 Docker 要求，无前端依赖。不内置完整 RBAC、菜单、部门、租户、工作流、
低代码 CRUD、插件市场、SSO/OAuth/OIDC 或监控平台。
不构建通用 CRUD 框架、自动路由扫描或复杂 IoC；不提供默认管理员凭据。

## 开发与质量检查

需要 Python >= 3.11，以及 [uv](https://docs.astral.sh/uv/getting-started/installation/)。
在仓库根目录执行：

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

发布时还需执行覆盖率检查和三数据库在线测试；完整可复制命令见
[测试指南](docs/testing.md#发布质量)和[发布验收](docs/release.md)。普通 `pytest` 使用临时 SQLite，
不要求外部服务，也不会把未运行的 PostgreSQL/MySQL 测试计为通过。

`uv sync` 可编辑安装当前项目及默认 dev 依赖组；`uv.lock` 保存已验证的解析结果。
运行时依赖包括 FastAPI、Pydantic、pydantic-settings、structlog、Uvicorn、
SQLAlchemy asyncio、aiosqlite、Alembic、argon2-cffi、PyJWT、email-validator 和 python-multipart；
项目 CLI 使用 Typer；命令、退出码和只读诊断范围见 [cli](docs/cli.md)。
asyncpg/asyncmy、OSS/COS SDK 按 extra 安装，HTTPX 仅用于测试。
开发组另装 PyJWT 的 crypto extra 以支持严格类型检查，HS256 运行时不依赖 cryptography。
项目使用标准 Python 构建接口，并不依赖 uv 专有打包格式。

修改代码后可用 `uv run ruff format .` 格式化。
激活虚拟环境后，也可直接执行 `ruff`、`pyright` 和 `pytest`。
安装步骤、提交约定和 PR 清单见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 仓库结构

```text
app/          bootstrap/、core/、common/、database/、providers/、infrastructure/、modules/{user,auth,file}/、cli/
tests/        conftest.py、unit/、integration/、api/
docs/         主题设计文档
data/         SQLite 和本地文件运行数据，内容不提交
alembic/      异步迁移环境、模板与 versions/
```

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [architecture](docs/architecture.md) | 分层、模块与目标目录 |
| [Project Structure](docs/Project%20Structure.md) | M0–M9 实际代码树、设计对齐与保留差异 |
| [coding-convention](docs/coding-convention.md) | 类型、代码风格、依赖政策 |
| [database](docs/database.md) | 数据模型、事务、迁移与兼容性 |
| [api](docs/api.md) | URL、序列化、分页与 OpenAPI |
| [errors](docs/errors.md) | 响应、错误描述符与 HTTP 映射 |
| [security](docs/security.md) | 认证、授权与安全默认值 |
| [configuration](docs/configuration.md) | 配置来源、装配与生命周期 |
| [extensions](docs/extensions.md) | Provider、Adapter 与可选依赖 |
| [storage](docs/storage.md) | 文件资源、存储与补偿 |
| [celery](docs/celery.md) | 独立 Worker、任务边界与异步桥接 |
| [logging](docs/logging.md) | 结构化事件、上下文与脱敏 |
| [testing](docs/testing.md) | 当前检查与后续测试要求 |
| [cli](docs/cli.md) | 项目命令、只读诊断和管理员创建 |
| [reference-modules](docs/reference-modules.md) | auth/user/file 的职责与验收 |
| [roadmap](docs/roadmap.md) | M0–M10、产品边界与发布门槛 |
| [release](docs/release.md) | M9 验证记录、兼容性矩阵、部署与已知限制 |
| [audit](docs/audit.md) | M0–M9 全量审计、复现修复、可靠性边界与复核结果 |
| [CHANGELOG](CHANGELOG.md) | 版本变更记录 |

## 路线图

M0 仓库基础 → M1 启动与配置 → M2 日志/响应/错误 → M3 数据库 →
M4 User → M5 Auth → M6 Storage/File → M7 Redis/Celery → M8 CLI →
M9 Release Hardening → M10 正式发布验收。M9 按本次范围合并兼容性、质量与文档加固，
正式发布仍需维护者确认发布清单，完整验收见 [roadmap](docs/roadmap.md)。

## 许可证

使用 [MIT License](LICENSE)。版权年份为 2026，版权主体仍待维护者在发布前填写。
