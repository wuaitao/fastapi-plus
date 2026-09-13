# 配置与生命周期

M1 已实现 `app/core/config/`、应用工厂、集中生命周期与显式路由注册。
M2 增加日志配置、请求上下文和集中异常/响应装配。
M3 增加数据库 URL 校验、异步引擎和 Session 生命周期。
M5 增加 JWT 秘密与 access/refresh 有效期。
M6 增加存储后端、Local 根目录、可选云配置和上传大小限制。
M7 增加可选 Redis 客户端、Celery Broker/结果后端和独立 Worker。
M8/M9 补齐独立 CLI 装配及发布验收；本页描述当前实现。

## 当前配置与运行

`Settings` 使用不可变的 pydantic-settings 模型，`get_settings()` 按进程缓存。
`core/config/` 下的 app、database、security、logging、storage、redis、celery
分组均继承 BaseSettings，由 `settings.py` 组合后统一加载来源。
单项能力校验留在对应分组，生产环境等跨分组约束留在 Settings；应用统一使用 Settings。
显式构造参数 > 环境变量 > 当前工作目录的 UTF-8 `.env` > 默认值。
普通配置采用以下平铺名称；云配置使用 `STORAGE_OSS__` / `STORAGE_COS__` 嵌套字段。
未知 `.env` 字段会报错。

| 环境变量 | Settings 字段 | 默认值 | 校验 |
| --- | --- | --- | --- |
| `ENVIRONMENT` | `environment` | `development` | development / testing / production 枚举 |
| `DEBUG` | `debug` | `false` | 布尔值；生产环境禁止开启 |
| `OPENAPI_ENABLED` | `openapi_enabled` | `true` | 独立控制 OpenAPI、Swagger UI 和 ReDoc 入口 |
| `LOG_FORMAT` | `log_format` | 未设置 | console / json；未设置时开发/测试为 console，生产为 json |
| `LOG_LEVEL` | `log_level` | `INFO` | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `DATABASE` | `database` | `sqlite` | sqlite / postgresql / mysql |
| `DATABASE_URL` | `database_url` | `sqlite+aiosqlite:///./data/app.db` | SecretStr；与 DATABASE 匹配的异步驱动，外部数据库要求主机及数据库名 |
| `JWT_SECRET` | `jwt_secret` | 未设置 | SecretStr，不出现在 repr 或配置序列化中；配置时至少 32 字节，生产必填 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `access_token_expire_minutes` | `30` | 1–1440 分钟 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `refresh_token_expire_days` | `7` | 1–365 天 |
| `STORAGE_BACKEND` | `storage_backend` | `local` | local / oss / cos；云默认后端必须配置相应字段 |
| `STORAGE_LOCAL_ROOT` | `storage_local_root` | `data/storage` | 本地存储根目录 |
| `STORAGE_OSS__*` | `storage_oss` | 未设置 | bucket、region、access_key_id、access_key_secret；配置即启用 |
| `STORAGE_COS__*` | `storage_cos` | 未设置 | 同上；COS 密钥对应 SecretId/SecretKey |
| `FILE_MAX_SIZE` | `file_max_size` | `10485760` | 正整数，单位字节 |
| `REDIS_ENABLED` | `redis_enabled` | `false` | 开启时要求 REDIS_URL 和 redis extra |
| `REDIS_URL` | `redis_url` | 未设置 | SecretStr；开启时要求 redis/rediss URL 与主机 |
| `CELERY_ENABLED` | `celery_enabled` | `false` | 开启时要求 CELERY_BROKER_URL 和 celery extra |
| `CELERY_BROKER_URL` | `celery_broker_url` | 未设置 | SecretStr；开启时要求有效 URL，传输由 Celery 选择 |
| `CELERY_RESULT_BACKEND` | `celery_result_backend` | 未设置 | SecretStr；可选 URL，未配置时忽略结果 |

在仓库根目录执行 `uv run uvicorn app.main:app --reload`。
`app/main.py` 只导入工厂并执行 `app = create_app()`。
工厂接受显式 Settings，保存在各自的 `app.state.settings`；省略时使用缓存配置。
`GET /health` 返回 HTTP 200 和 `{"status":"ok"}`，仅表示应用存活。
`bootstrap/routers.py` 显式调用 `include_router`，新增路由时在此注册。

`bootstrap/lifespan.py` 统一调用 startup/shutdown 钩子，异常退出也执行 shutdown。
启动创建应用独立的 Engine 和 Session 工厂，关闭时释放引擎；连接按需建立。
启动不执行建表、迁移或业务初始化，Health 不检查数据库连通性。
开发/测试未配置 JWT_SECRET 时，应用工厂生成随机临时密钥；重启后旧令牌失效。
多进程部署必须显式配置相同随机秘密，不输出或提交该值；生产缺失秘密时立即失败。
TokenProvider、NullTokenStore 属于应用级资源；启动仍不创建任何用户或管理员。
它们与 StorageRegistry 统一在 `bootstrap/providers.py` 装配；异常与中间件分别由
`bootstrap/exceptions.py`、`bootstrap/middleware.py` 注册。
存储完整示例见 [storage](storage.md)；任务启动与调用见 [celery](celery.md)。
Web Lifespan 按 Engine → Redis → Celery 顺序创建可选资源，逆序关闭；中途失败也清理。
启用 Redis 时执行 PING，连接/命令超时均为 5 秒；`app.state.redis` 禁用时为 None。
启用 Celery 时检查 Broker 连接，阻塞检查在线程执行；`app.state.celery` 禁用时为 None。
Web 不启动 Worker/Beat，不注册或执行任务；Health 仍只表示应用存活。
Redis 应用客户端和 Celery Redis Broker 的开关独立，使用 Redis Broker 不要求 REDIS_ENABLED=true。
测试清理环境变量、在临时目录加载 `.env`，并在每个用例前后清理 Settings 缓存。

## 类型化配置

使用 pydantic-settings。生产使用环境变量，本地可使用不提交的 `.env`；
来源优先级为环境变量 > .env > 默认值，测试可显式提供独立 Settings。
配置按 app、database、security、logging、storage、redis、celery 等实际能力组合，
不一次性创建所有未来字段。

环境值统一为 development、testing、production。
默认目标为 SQLite、Local、Redis disabled、Celery disabled。
环境变量具体别名随对应里程碑实现并记录，不同时维护多套前缀/嵌套写法。
`REDIS_ENABLED=false`、`CELERY_ENABLED=false` 保持默认关闭；未启用时不导入第三方包或连接服务。

秘密使用 SecretStr 等安全表达，不能通过 repr、错误或日志泄漏。
生产 debug/SQL echo 默认关闭，缺失必要秘密立即失败。
OpenAPI 可见性独立配置，不简单绑定生产环境开关。

只校验已启用组件的必要配置：Local 不要求云凭据，
禁用 Redis 不要求 URL。已启用但配置不全、依赖缺失或资源不可用时启动失败。

配置启动后视为不可变；业务模块不调用 os.getenv，不按环境名称散布业务分支。
动态业务设置属于业务数据，不混入应用 Settings。

## 装配与入口

工厂签名为 `create_app(settings: Settings | None = None) -> FastAPI`。
工厂负责 FastAPI 创建、Middleware/Handler/Router 注册、Lifespan 与 OpenAPI 装配。
main.py 只调用工厂；不自动建表、迁移、seed 或创建管理员。

具体实现仅在 Bootstrap/Composition Root 选择。
CLI 与 Worker 独立装配，不导入 app.main 或复用 Web 进程资源实例。

## 资源作用域

| 作用域 | 资源 |
| --- | --- |
| 应用/进程 | Settings、Engine、连接池、Storage/HTTP 客户端 |
| 请求 | AsyncSession、当前用户、request_id |
| 身份查询 | 独立短 AsyncSession，鉴权返回前关闭，当前用户作为已加载快照使用 |
| 任务 | 独立 Session、任务上下文、correlation_id |

不把 Current User、Request、Session 或业务数据保存到全局 app.state。
每个入口获取和关闭自己的资源，Service 仍拥有业务事务。

Web 统一使用 bootstrap/lifespan 管理资源。
先配置与日志，再数据库、已启用 Redis、Storage 和所需客户端；
关闭时反向释放，启动中途失败也要清理已创建资源。
不强制每个 Provider 实现空的生命周期方法。

Middleware 保持无业务，认证授权放依赖。当前中间件处理请求 ID、访问日志与安全错误输出；
未内置 CORS 或通用安全响应头配置。业务以后新增这些原生中间件时，须通过行为测试验证
正常及异常路径的顺序，避免各模块分散注册。

## 验收

验证默认配置、非法环境、生产秘密缺失、选定后端配置、
可选组件禁用导入、启用失败、资源释放及测试替换。
测试不能偷偷读取开发者 .env，也不访问真实生产服务。
