# 架构

本文描述 M0–M9 已实现的 v0.1 架构；最终复核见 [全量审计](audit.md)。
[设计代码树](Project%20Structure.md) 记录目录职责；不为目录对称预建空文件。

## 产品模型

FastAPI Plus 是面向生产的轻量后端 Starter，采用 **Template-first**：
应用代码直接保留在模板的 `app/`，不提前抽成独立框架包。
标准 Python 打包用于可靠安装与导入，不改变模板产品模型。

架构关键词：**Lightweight / Explicit / Modular / Replaceable / Predictable**。

> Secure by default. Extensible by design. Minimal in core. Explicit is better than magic.

产品范围与发布验收以 [roadmap](roadmap.md) 为准。

## 层次与依赖

```text
HTTP Router / CLI / Celery Task
              ↓
           Service
              ↓
     Repository / Provider
              ↓
        Infrastructure
```

这是运行调用方向。代码依赖上，Infrastructure 实现 Provider 契约，
Provider 不导入具体 Adapter；由 Bootstrap 选择实现并注入业务层。

| 层 | 职责 | 禁止 |
| --- | --- | --- |
| Router | 输入解析、声明依赖与权限、调用 Service、输出 Schema | SQL、业务流程、厂商 SDK、逐路由重复转换业务异常 |
| Service | 业务规则、协调 Repository/Provider、业务事务、应用结果 | Request、Depends、HTTPException、JSONResponse、厂商分支 |
| Repository | SQLAlchemy 查询、add/flush/refresh、返回 ORM | commit、HTTP 行为、权限和业务流程 |
| Provider | 稳定且最小的应用能力契约 | 厂商类型、HTTP 请求对象、基础设施装配 |
| Infrastructure | 数据库与具体 Provider Adapter、成熟框架集成 | 反向依赖业务 Router、泄漏厂商 SDK 类型 |
| Bootstrap | 配置、工厂、显式注册和资源生命周期 | 业务初始化、隐式迁移、默认用户 |

Service 拥有业务 commit/rollback；入口管理资源作用域。
Repository 查询单个对象可返回 ORM 或 None，由 Service 决定“不存在”的业务含义。
Service 返回 ORM 或应用结果；Router 转换为 API 响应 Schema。
简单输入 DTO 可复用模块 Schema，不为分层增加 Entity/Mapper/Command 等重复对象体系。

## 目标目录职责

以下按对应里程碑逐步创建，M0 不预建整棵运行时目录树：

| 路径 | 职责 |
| --- | --- |
| `app/main.py` | 仅调用应用工厂 |
| `app/bootstrap/` | application、lifespan、routers、providers 与入口装配 |
| `app/core/` | config、security、exceptions、logging 等稳定横切能力 |
| `app/common/` | 无业务含义的响应、分页和公共类型 |
| `app/database/` | SQLAlchemy engine、session、base、mixins 与最小 Repository 基础 |
| `app/providers/` | StorageProvider、TokenStore 能力契约 |
| `app/infrastructure/` | storage、redis、celery 与所需共享客户端 |
| `app/modules/` | auth、user、file 自包含参考模块 |
| `app/cli/` | 当前项目的命令入口 |
| `alembic/` | 迁移环境、模板与 versions 源文件 |
| `tests/` | unit、integration、api，按模块继续组织 |
| `data/` | SQLite 与本地存储运行数据，不属于源码 |

模块推荐文件为 `model.py`、`schema.py`、`repository.py`、`service.py`、
`router.py`、`dependencies.py`、`errors.py`，按实际需要创建。
Auth 无需为结构对称创建 model/repository；任务文件在 M7 按需增加。

## 显式装配与复用

路由统一在 `bootstrap/routers.py` 注册，不扫描目录。
模块特定依赖留在模块；跨领域资源依赖放 Core/Infrastructure。
涉及用户查询的认证流程属于 auth，Core Security 保留密码、Token 等基础能力。

当前装配及公共能力的具体位置：

- `bootstrap/application.py` 调用 `exceptions.py`、`middleware.py`、`providers.py`
  和 `routers.py` 的显式注册函数，`lifespan.py` 管理资源生命周期。
- `core/config/settings.py` 组合 app/database/security/logging/storage/redis/celery
  配置分组，保留既有平铺环境变量；Redis/Celery 分组包含默认关闭开关和连接配置。
- `core/exceptions/` 分开描述符、公共错误、异常类及 HTTP Handler；包入口不导入 Handler。
- `core/logging/` 分开日志配置、请求上下文和脱敏，Bootstrap 只负责注册。
- `core/security/dependencies.py` 解析 Bearer，`permissions.py` 实现通用权限策略；
  `modules/auth/dependencies.py` 装配 Service、查询当前用户并将其状态交给权限策略。
- `database/session.py` 提供请求依赖 `get_session` 和独立入口的 `session_scope`；
  业务模块不反向导入 Bootstrap。
- `providers/token_store.py` 合放 TokenStore 契约和无外部依赖的 NullTokenStore，由 Bootstrap 注入。
  空实现只表达默认无状态策略，不是厂商 Adapter；将来引入 Redis 等真实存储时，具体实现仍放 Infrastructure。
  `common/pagination.py` 保存 `Page` 和 `PageResult`，不依赖 ORM。

相对目标树保留的辅助文件及尚未创建的规划文件见
[代码树落地说明](Project%20Structure.md#设计对齐与保留差异)。

使用 FastAPI 原生 Depends、普通工厂和 Composition Root。
CLI、Worker 独立装配所需资源并复用同一 Service，不导入全局 Web 应用。
资源作用域与生命周期详见 [configuration](configuration.md)。

当前用户依赖先在独立短 Session 中调用 AuthService，关闭身份查询事务后返回已加载的用户快照。
该快照仅用于鉴权和响应，不绑定业务 Session；必选与可选身份解析共用这一路径。
业务 Service 继续使用请求级 Session，避免认证读锁延续到 SQLite 写事务中。

仅抽象业务能力，不重新包装 FastAPI、SQLAlchemy、Alembic、Pydantic 或 Celery。
最小 Repository 复用不扩展成通用 Service/Router、查询 DSL 或 CRUD 平台。

M9 通过独立解释器检查公共契约、Service、CLI 的传递导入边界，
并用 AST 检查 Repository 不提交/回滚、Router 不导入 SQLAlchemy/Repository/Adapter 或操作事务。
已审查 Auth/User/File、Bootstrap、CLI 与 Worker 的业务调用路径；这些测试是明确边界的回归保护，
不代替人工判断业务职责。验证记录见 [发布验收](release.md)。
