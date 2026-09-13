# 扩展与可选基础设施

v0.1 使用 Provider / Adapter / Module 扩展；M6 已实现 StorageProvider 与三种 Adapter。

## 最小能力边界

Provider 描述应用需要的稳定能力，Adapter 在 Infrastructure 中实现，
业务模块使用契约。Bootstrap 显式选择具体实现，不让 Service 判断厂商名称。

当前能力契约为 StorageProvider、TokenStore；CacheProvider 仍属预留能力。
契约使用普通类型与轻量应用结果，不泄漏 SDK 类型或 FastAPI Request。
只抽象实际使用的能力，不把所有 Redis 命令包装成万能 Service。
TokenStore 与无外部依赖的 NullTokenStore 合放在 `providers/token_store.py`；
空实现表达默认无状态策略，真实 Redis 等 Adapter 仍应放在 Infrastructure。

FastAPI、SQLAlchemy、Alembic、Pydantic、Celery 保持原生。
Celery 仅集成配置、Worker 装配、日志与异步桥接，不再创建平行任务框架。

## 可选依赖契约

- 未安装且未启用：核心导入、启动与默认流程正常。
- 显式启用：验证必要配置与依赖，失败给出安全、可操作的提示。
- 只在选择对应 Adapter 时加载厂商 SDK；不在包导入时全量导入。
- 默认不连接 Redis、不启动 Celery，不要求云账号。

可选能力与版本以 pyproject/uv.lock 为准。已提供 postgresql/mysql/oss/cos/redis/celery extras；
Redis 客户端和 Celery 已在 M7 实现。StorageRegistry 在 `bootstrap/providers.py` 显式装配，
配置与真实云验证入口见 [storage](storage.md)。

Redis 基础设施管理客户端、连接池与生命周期；尚未提供 CacheProvider 或 RedisTokenStore。
启用 Redis 不改变默认 NullTokenStore 的无状态退出语义；Celery Broker 与应用 Redis 配置独立。
不因可复用 Redis 就提前实现限流、分布式锁或动态系统设置。

## 扩展流程与边界

增加实现时先明确现有契约，编写 Adapter 和契约测试，
在 Composition Root 显式注册，再更新配置与使用文档。
只有真实需求需要新能力时才修改 Provider，并同步所有实现和测试。

v0.1 不包含动态插件加载、运行时安装、插件市场、自动路由扫描、
复杂 IoC、Event Bus 或配置驱动的业务 DSL。
Mail、SSO、审计 Sink、监控、更多存储后端可以后续扩展，
不提前创建空接口文件或加入默认安装。
