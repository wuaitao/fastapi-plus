# FastAPI Plus v0.1 Project Structure

本页以原设计的分层和目录职责为准，列出 M0–M9 最终审计后的实际交付代码树。
Celery 基类、信号和 Redis/Celery 集成测试已向设计归位；不以创建空文件补齐尚无调用方的规划项。
原设计中的预留能力、必要辅助文件及 TokenStore 精简决定见下方说明；审计证据见 [全量审计](audit.md)。
运行目录、虚拟环境、缓存及构建产物不属于交付源码，不列入此树。

```text
fastapi-plus/
├── alembic/
│   ├── versions/
│   │   ├── 0001_create_users.py
│   │   └── 0002_create_files.py
│   ├── env.py
│   └── script.py.mako
├── app/
│   ├── bootstrap/
│   │   ├── __init__.py
│   │   ├── application.py
│   │   ├── cli.py
│   │   ├── exceptions.py
│   │   ├── lifespan.py
│   │   ├── middleware.py
│   │   ├── providers.py
│   │   ├── routers.py
│   │   └── worker.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── doctor.py
│   │   ├── main.py
│   │   └── user.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── pagination.py
│   │   └── response.py
│   ├── core/
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── app.py
│   │   │   ├── celery.py
│   │   │   ├── database.py
│   │   │   ├── logging.py
│   │   │   ├── redis.py
│   │   │   ├── security.py
│   │   │   ├── settings.py
│   │   │   └── storage.py
│   │   ├── exceptions/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── common.py
│   │   │   ├── descriptors.py
│   │   │   ├── handlers.py
│   │   │   └── middleware.py
│   │   ├── logging/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── context.py
│   │   │   └── redaction.py
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── password.py
│   │   │   ├── permissions.py
│   │   │   └── token.py
│   │   └── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── diagnostics.py
│   │   ├── engine.py
│   │   ├── metadata.py
│   │   ├── mixins.py
│   │   ├── repository.py
│   │   └── session.py
│   ├── infrastructure/
│   │   ├── celery/
│   │   │   ├── __init__.py
│   │   │   ├── app.py
│   │   │   ├── base.py
│   │   │   ├── bridge.py
│   │   │   ├── config.py
│   │   │   └── signals.py
│   │   ├── redis/
│   │   │   ├── __init__.py
│   │   │   └── client.py
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── aliyun_oss.py
│   │   │   ├── common.py
│   │   │   ├── local.py
│   │   │   └── tencent_cos.py
│   │   ├── __init__.py
│   │   └── diagnostics.py
│   ├── modules/
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── router.py
│   │   │   ├── schema.py
│   │   │   └── service.py
│   │   ├── file/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   ├── model.py
│   │   │   ├── repository.py
│   │   │   ├── router.py
│   │   │   ├── schema.py
│   │   │   └── service.py
│   │   ├── user/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   ├── model.py
│   │   │   ├── repository.py
│   │   │   ├── router.py
│   │   │   ├── schema.py
│   │   │   ├── service.py
│   │   │   └── tasks.py
│   │   └── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── storage.py
│   │   └── token_store.py
│   ├── __init__.py
│   └── main.py
├── data/
│   └── .gitkeep
├── docs/
│   ├── Project Structure.md
│   ├── api.md
│   ├── architecture.md
│   ├── audit.md
│   ├── celery.md
│   ├── cli.md
│   ├── coding-convention.md
│   ├── configuration.md
│   ├── database.md
│   ├── errors.md
│   ├── extensions.md
│   ├── logging.md
│   ├── reference-modules.md
│   ├── release.md
│   ├── roadmap.md
│   ├── scaffold-review.md
│   ├── security.md
│   ├── storage.md
│   └── testing.md
├── tests/
│   ├── api/
│   │   ├── modules/
│   │   │   ├── auth/
│   │   │   │   ├── conftest.py
│   │   │   │   ├── test_auth.py
│   │   │   │   └── test_concurrency.py
│   │   │   ├── file/
│   │   │   │   ├── conftest.py
│   │   │   │   └── test_file.py
│   │   │   └── user/
│   │   │       ├── conftest.py
│   │   │       └── test_user.py
│   │   ├── test_core.py
│   │   ├── test_cors.py
│   │   ├── test_database.py
│   │   ├── test_health.py
│   │   └── test_release_openapi.py
│   ├── integration/
│   │   ├── celery/
│   │   │   └── test_worker.py
│   │   ├── cli/
│   │   │   └── test_cli.py
│   │   ├── database/
│   │   │   ├── test_database.py
│   │   │   ├── test_database_lifecycle.py
│   │   │   ├── test_diagnostics.py
│   │   │   ├── test_migrations.py
│   │   │   └── test_release.py
│   │   ├── modules/
│   │   │   ├── file/
│   │   │   │   └── test_service.py
│   │   │   └── user/
│   │   │       └── test_service.py
│   │   ├── redis/
│   │   │   └── test_client.py
│   │   ├── storage/
│   │   │   ├── test_contract.py
│   │   │   └── test_diagnostics.py
│   │   ├── conftest.py
│   │   └── test_application.py
│   ├── unit/
│   │   ├── common/
│   │   │   └── test_responses.py
│   │   ├── core/
│   │   │   ├── test_exceptions.py
│   │   │   ├── test_import_boundaries.py
│   │   │   ├── test_logging.py
│   │   │   ├── test_optional_infrastructure.py
│   │   │   ├── test_security.py
│   │   │   └── test_settings.py
│   │   ├── database/
│   │   │   └── test_database.py
│   │   ├── modules/
│   │   │   ├── file/
│   │   │   │   └── test_errors.py
│   │   │   └── user/
│   │   │       └── test_errors.py
│   │   ├── providers/
│   │   │   └── test_storage.py
│   │   └── test_foundation.py
│   ├── conftest.py
│   ├── database_models.py
│   ├── manual_optional_infrastructure.py
│   ├── manual_storage_cloud.py
│   └── storage_fakes.py
├── .env.example
├── .gitattributes
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── alembic.ini
├── pyproject.toml
└── uv.lock

```

## 设计对齐与保留差异

| 原位置 | 最终位置 | 原因 |
| --- | --- | --- |
| `app/infrastructure/celery/task.py` | `app/infrastructure/celery/base.py` | BaseTask 与有限重试符合设计中的基类职责 |
| `app/infrastructure/celery/logging.py` | `app/infrastructure/celery/signals.py` | 发布上下文、Worker 日志均通过 Celery signal 接入 |
| `tests/integration/test_redis.py` | `tests/integration/redis/test_client.py` | 与被测基础设施归属一致 |
| `tests/integration/test_celery.py` | `tests/integration/celery/test_worker.py` | 归入设计中的 Celery 集成目录 |
| `app/infrastructure/token_store.py` | 合入 `app/providers/token_store.py` | NullTokenStore 没有 I/O、厂商或资源职责，空实现无需独立 Adapter 文件 |

以上原路径不保留转发文件；调用方、测试导入与文档同步更新。
TokenStore 保留 Protocol，AuthService 继续依赖契约，Bootstrap 显式注入 NullTokenStore。
未来 RedisTokenStore 等有实际外部依赖的实现仍放在 `infrastructure/redis/`，不反向导入到 Provider。
同文件合放空实现不会让公共契约引入 Redis、FastAPI、SQLAlchemy 或业务模块。

保留的辅助文件有当前调用方：

- `core/exceptions/middleware.py` 承接原请求上下文中的未知异常兜底，使错误响应可经过外层 CORS。
- `database/metadata.py` 显式注册迁移模型，避免自动扫描；`database/diagnostics.py` 执行只读迁移检查。
- `infrastructure/diagnostics.py` 集中 CLI 所需的外部能力探测；`infrastructure/storage/common.py` 共享安全键名和阻塞调用边界。
- `modules/user/tasks.py` 保存唯一只读任务与 Handler 示例，沿用 M7 已实现范围。
- `tests/database_models.py` 使用独立 metadata，`storage_fakes.py` 只模拟云 SDK 边界；两个 manual 文件保留显式外部验收入口。
- `docs/release.md` 保留发布流程与原 M9 验证记录，`docs/audit.md` 记录最终审计与本次复验。

原设计中的以下项不创建空壳，也不视为未完成的当前功能：

- `common/{types,enums,utils}.py`：类型保留实际领域归属，无需通用杂物模块。
- `providers/{cache,mail}.py`、`infrastructure/redis/{cache,token_store}.py`、`infrastructure/http/`：当前没有缓存、邮件、撤销存储或 HTTP 客户端业务调用方。
- `modules/auth/errors.py`：认证使用 Core 共享错误和 User 状态错误，尚无 Auth 专属描述符。
- `modules/file/{handlers,tasks}.py`：文件上传不依赖 Worker，任务示例已位于 user 模块。
- `tests/unit/modules/auth/`：现有安全基础测试在 `unit/core/`，真实认证流程在 `api/modules/auth/`，不为空目录新增测试。
- `data/storage/{public,private}`：运行时按需创建，不提交数据库或文件内容。

配置分组、异常分工、显式 Bootstrap、模块 Repository/Service/Router 保留原设计。
这些边界承担配置校验、框架转换、入口装配或模块复用职责，不按文件行数机械合并。
新增模块仍采用参考模块的显式注册方式；产品范围以 [roadmap](roadmap.md) 为准。

## Architecture Boundaries

核心调用方向：

```text
Router
  ↓
Service
  ↓
Repository / Provider
  ↓
Infrastructure
```

应用入口：

```text
                 Service
              ↗     ↑     ↖
         FastAPI   CLI   Celery
```

职责划分：

```text
bootstrap/
    应用装配、Composition Root、生命周期

core/
    全局稳定基础能力

common/
    无业务含义的公共类型和 Schema

database/
    SQLAlchemy 基础设施

providers/
    对外能力抽象契约

infrastructure/
    Provider 的具体技术实现

modules/
    业务模块，自包含

cli/
    命令行入口
```

## v0.1 Reference Modules

仅包含：

```text
auth
user
file
```

禁止继续扩展为默认：

```text
role
menu
department
tenant
workflow
dictionary
notification
```

## Default Runtime

默认运行只要求：

```text
Python 3.11+
SQLite
Local filesystem
```

默认：

```text
Redis disabled
Celery disabled
Storage = local
Database = SQLite
```

## Primary Toolchain

```text
uv
Ruff
Pyright
Pytest
Alembic
SQLAlchemy 2.x
FastAPI
Pydantic v2
```
