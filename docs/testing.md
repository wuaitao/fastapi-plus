# 测试

## 当前测试基础

保留 M0 的安装元数据、app 包导入与异步工具链测试。
M1 增加配置默认值、来源优先级、缓存、不可变性与非法输入测试；
验证工厂隔离、启动/关闭钩子和异常退出、Health 与 OpenAPI 的响应和可见性。
M2 增加泛型响应/分页、错误描述符唯一性、日志输出/脱敏，以及真实请求的
422/404/405/500、请求 ID 生成/复用、并发与线程池上下文、流式异常和 OpenAPI 契约测试。
M3 增加真实 SQLite 引擎/Session、Repository CRUD/分页、唯一和外键约束、
显式与退出回滚、UTC、DDL/SAVEPOINT 事务、请求资源关闭和日志保护测试。
Alembic 在临时目录生成迁移并执行升级、检查、降级和再次升级，不写入仓库 versions。
测试模型使用独立 metadata，不污染应用迁移目标。

M4 增加 `tests/{layer}/modules/user/`：API 使用真实 users 迁移及独立请求 Session，
覆盖 CRUD、重复 username/email、空邮箱、分页、校验、敏感字段限制及 OpenAPI。
集成测试覆盖不提交的 Repository、唯一约束竞争、更新冲突、提交失败回滚和非唯一错误传播。
SQLite 验证 users 迁移升级/降级/再升级及 metadata 一致性；三方言验证离线 SQL。

M5 增加 Core Security 单元测试及 `tests/api/modules/auth/`，使用真实 users 迁移、
独立请求 Session 和完整 Bearer 依赖链，覆盖密码/声明/签名/有效期/类型混用、
登录失败一致性、刷新、当前用户、禁用/删除后的状态检查、无状态退出、401/403、
管理员 CRUD、自删限制、空库无默认账号、秘密脱敏及 OpenAPI。
UserService 集成测试独立验证自删规则；原有 CRUD API 用例仅覆盖当前用户依赖，
保留空库分页等原有断言，真实权限链由 Auth API 测试验证。
开发组安装 PyJWT 的 crypto extra，以补齐其可选类型注解；HS256 运行时仅需 PyJWT。

`tests/conftest.py` 提供仓库路径、独立 Settings 和自动配置来源隔离。
同时恢复进程日志配置与 contextvars，避免测试之间共享请求字段或已关闭的捕获流。
`tests/unit/core/` 验证配置、异常、日志及安全，`tests/unit/common/` 验证响应和分页，
`tests/unit/database/` 验证数据库配置与方言，`tests/unit/providers/` 验证存储契约和装配。
`tests/integration/` 验证工厂与生命周期，数据库与迁移用例归入 `database/`，
`tests/api/` 使用 HTTPX AsyncClient/ASGITransport 调用真实应用，显式进入 Lifespan。

`tests/integration/conftest.py` 使用 tmp_path 创建 SQLite 文件，无包裹测试的外层事务，
确保 commit/rollback 真实执行。测试建表仅用于 Repository 用例，迁移用例单独验收。
三方言单元测试验证主键编译，迁移测试验证三方言离线 SQL；可选驱动未安装时验证明确错误，
安装后验证真实异步引擎构造（不连接服务器）。可使用 `uv sync --all-extras` 检查全部驱动。
普通测试不依赖 MySQL/PostgreSQL 服务；M9 提供显式选择数据库的在线矩阵，
使用方法和实际验证版本见 [发布验收](release.md#三数据库在线验证)。

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Pytest 使用 importlib 导入模式，不通过 sys.path 修改掩盖安装问题；
strict-config/strict-markers 防止配置拼写错误被忽略。
pytest-asyncio 使用 strict 模式，异步测试显式标记 asyncio，
异步 fixture 使用 pytest_asyncio.fixture，默认循环作用域为 function。
参见 [pytest-asyncio 配置](https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html)。

## 当前测试分层

M8 使用 Typer CliRunner 与已安装入口验证 CLI；临时项目执行真实 Alembic 迁移往返，
验证 doctor 不创建数据库/目录/版本表、迁移落后与可选组件故障安全输出。
管理员流程复用真实 UserService、Argon2id 和 SQLite，覆盖密码隐藏与确认、非法输入、
唯一冲突及提交失败回滚；独立解释器验证 CLI 不导入 Web app 或禁用的可选 SDK。

M7 新增可选 Redis/Celery 配置、缺失依赖与禁用启动、独立 Worker 导入边界测试。
真实 redis-py 连接使用临时协议端点验证生命周期，SQLite 验证 Handler、独立 Session、
退出回滚、Engine/循环释放；Celery tracer 验证有限重试，memory Broker 的非 eager Worker
验证 JSON、关联上下文及清理。开发组安装 Celery/Redis 和 celery-types，核心运行时依赖不变。
`tests/manual_optional_infrastructure.py` 显式启动临时 Redis 和另一个进程的 Worker，
验证真实 Broker/结果后端路径；运行方式见 [celery](celery.md)。

M6 新增 Storage Registry/可选导入测试、真实 Local 和 OSS/COS 共同行为契约，
以及真实文件 API、所有权、public/private、路径/链接逃逸、Unicode、较大流测试。
真实数据库验证 files 迁移与 metadata 一致性、上传写入/提交失败补偿及补偿失败、
删除两阶段失败和历史 backend 选择。三方言离线迁移不等同于在线数据库验证。
文件 Service 集成用例位于 `tests/integration/modules/file/test_service.py`，
文件错误用例位于 `tests/unit/modules/file/test_errors.py`，存储 Adapter 契约留在
`tests/integration/storage/`。移动测试保留原有断言及共享 fixture 作用域。
真实云测试为显式入口 `tests/manual_storage_cloud.py`，不进入默认收集，详见 [storage](storage.md)。

目录调整回归增加配置分组组合后的来源优先级、云嵌套字段与秘密保护测试，
并在独立解释器中阻止公共契约导入业务/Adapter/Web 装配、阻止 Service 导入
Bootstrap/Adapter/FastAPI，避免包初始化隐式破坏依赖方向。

| 层 | 关注 | 边界 |
| --- | --- | --- |
| unit | 业务规则、Schema、应用结果与异常 | Service 可用简单 fake Repository/Provider |
| integration | Repository、迁移、Storage/Redis Adapter、任务与资源作用域 | 数据库/本地文件系统尽量真实 |
| api | HTTP、权限、响应、依赖装配、OpenAPI | 真正 FastAPI 应用与 HTTPX 客户端 |

业务测试按 tests/{layer}/modules/{module} 组织，按需创建目录。
不 Mock 当前被测组件，不用 Mock SQLAlchemy 代替 Repository 集成测试。
云 SDK 和外部服务是可模拟边界，但 Adapter 自身仍执行真实映射与异常逻辑。

## 隔离与确定性

测试彼此独立，不依赖执行顺序、固定端口或共享业务数据。
默认 function scope；昂贵资源共享时必须证明资源和事件循环隔离。
使用 tmp_path、测试 Settings 和独立数据库，不读取开发者 .env、
不修改 data/ 或真实存储目录，不使用生产凭据。

应用工厂就绪后通过显式 Settings 和 FastAPI dependency_overrides 替换依赖；
统一清理 override、Session 和上下文。
事务 fixture 必须真实覆盖 Service commit/rollback，不能让测试事务掩盖失败。

## 关键验收

- 数据库：真实 Repository、唯一冲突、分页、提交/回滚、空库迁移及模型与迁移一致性。
- API：正确状态码、泛型 envelope、字符串 ID、自定义 422、404/405/500、Bearer/OpenAPI。
- Security：密码哈希、签名/有效期/Token 类型、禁用用户、401/403、无默认账号、脱敏。
- Storage：统一 Provider 契约、真实 Local、安全路径、私有下载、流处理与数据库失败补偿。
- 可选能力：未安装且禁用不影响核心；启用失败明确；云 Adapter 普通测试可模拟 SDK。
- Celery：Handler、序列化、桥接、重试、幂等、资源与上下文；少量真实 Worker 验证。
- CLI：退出码、命令映射、只读 doctor、管理员创建复用 Service。

每个行为变更需要适当测试；修复缺陷应先验证可复现失败。
不删除失败用例、放宽断言或添加 skip/xfail 来隐藏问题。

## 发布质量

SQLite 提供默认快速反馈。v0.1 发布前 MySQL、PostgreSQL、SQLite
均需通过核心 Repository、参考模块与迁移测试；三数据库支持不是仅文档声明。
普通测试不要求云账号，真实云测试显式选择并使用专门最小权限测试凭据。

M9 使用开发依赖 coverage.py，统计完整 `app/` 的语句与分支，不配置额外的排除规则。
整体门槛为 >= 80%，Core、Security、Database 各自 >= 90%。从仓库根目录执行：

```bash
uv run coverage run -m pytest
uv run coverage report
uv run coverage report --include="app/core/*" --fail-under=90
uv run coverage report --include="app/core/security/*" --fail-under=90
uv run coverage report --include="app/database/*" --fail-under=90
```

整体 80% 门槛配置在 pyproject.toml；三个关键目录通过上述命令分别强制检查。
报告失败会返回非零退出码。`.coverage`、`htmlcov/`、`coverage.xml` 属于忽略的运行产物。
可执行 `uv run coverage html` 查看未覆盖分支；不以无意义测试或排除规则替代关键行为覆盖。

M9 增加 `tests/integration/database/test_release.py`：默认以临时 SQLite 进入完整迁移后的
Repository/Auth/User/File 流程，也可用 `--release-database=postgresql|mysql` 显式运行。
外部 URL 只从 `FASTPLUS_TEST_DATABASE_URL` 读取，必须后端匹配、库名以 `fastplus_test_` 开头且无表/视图；
测试结束释放应用连接、迁移往返并清理表。缺少配置或非空库直接失败，不跳过测试。
只使用专用空库，勿共享给并发测试进程；执行中断时由操作者检查并重建该专用测试库。

`tests/api/test_release_openapi.py` 遍历全部 schema 引用、唯一 operationId、描述、tags、
业务 envelope、自定义错误模型及字符串 ID；既有模块测试继续验证 Bearer 与二进制下载。
`tests/unit/core/test_import_boundaries.py` 同时验证传递导入和 Repository/Router 的静态边界。
这些验收不要求新增线上能力；M9 的实际结果与已知限制见 [release](release.md)。
最终审计补充真实 Bearer 认证后的并发创建（不同用户名均成功、同名返回 409），
以及上传校验取消时的线程/文件生命周期、只读存储诊断的链接拒绝用例。
Redis/Celery 集成测试按设计分别归入 `integration/redis/` 与 `integration/celery/`；
断言和共享 fixture 作用域保留，最终结果见 [全量审计](audit.md)。
质量门和 Definition of Done 见 [AGENTS](../AGENTS.md)。
