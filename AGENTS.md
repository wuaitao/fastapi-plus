# FastAPI Plus 工作约定

本文件是 Codex 与贡献者的操作契约，设计细节见 [README 文档导航](README.md#文档导航)。
坚持 Lightweight、Explicit、Modular、Replaceable、Predictable；采用 Template-first。

## 开始前与范围

1. 阅读本文件、[roadmap](docs/roadmap.md)和任务相关设计，检查现有代码与测试。
2. 明确假设、最小变更和验证方式；歧义按最终产品范围处理并报告。
3. 不重设计架构、不改无关内容、不提前实现后续里程碑。当前交付为 M9 Release Hardening。
4. 生成代码、配置或查询库 API 时使用 Context7 核实；不可用时说明并查官方资料。

## 架构与职责

运行方向：Router / CLI / Celery Task → Service → Repository / Provider → Infrastructure。
Infrastructure 实现 Provider 契约；契约不反向导入 Adapter，Bootstrap 显式装配。

- **Router**：解析 HTTP、声明依赖和认证授权、调用 Service、序列化 Schema。
  不写 SQL、业务流程或厂商 SDK，不逐路由重复捕获业务异常。
- **Service**：业务规则、协调 Repository/Provider、返回 ORM 或应用结果。
  拥有业务 commit/rollback；不依赖 Request、Depends、HTTPException、JSONResponse 或厂商实现。
- **Repository**：SQLAlchemy 数据访问、add/flush/refresh、返回 ORM。
  永不 commit，不做权限、HTTP 或业务流程。
- **Provider**：最小稳定应用能力契约；**Infrastructure**：具体实现与资源集成。
  SDK 类型和阻塞细节留在 Adapter。
- **Bootstrap**：工厂、显式路由/Provider 注册、生命周期；不初始化业务数据。
  请求/任务使用独立 Session，入口关闭资源，Service 完成事务。
- 业务按模块组织，模块依赖和错误放模块内，跨领域依赖放 Core/Infrastructure。
  CLI、Worker 复用 Service，独立装配，不导入全局 Web app。

详情见 [architecture](docs/architecture.md)、[database](docs/database.md)、
[extensions](docs/extensions.md)和[参考模块](docs/reference-modules.md)。

## 契约与安全

- Service 抛应用异常；稳定描述符包含数字 code、key、安全 message、HTTP status。
  未知异常集中处理，Router 不重复转换。
- JSON 业务 API 使用 code/message/data，保留 HTTP 语义及自定义 422；
  下载、流、重定向等不强制封装。见 [api](docs/api.md)、[errors](docs/errors.md)。
- 默认 SQLite、Local，支持 MySQL/PostgreSQL 与 OSS/COS；Redis/Celery 可选且默认关闭。
  未安装且未启用的可选能力不得影响核心。
- ID 默认数据库生成整数，禁止默认 Snowflake；Schema 按需字符串化。
  模型变更附迁移；启动不自动 migrate/create_all/创建管理员。
- 禁止默认凭据、硬编码生产秘密、输出密码/Token/SQL/SDK 内部错误。
  配置仅通过配置层读取，生产安全配置 fail fast。
- 私有文件不公开挂载，原始文件名不作路径；存储与数据库失败采用明确补偿。
  Celery 使用 JSON 参数、独立 Worker 和集中异步桥接。
- 日志使用 structlog，敏感值脱敏，不默认记录完整请求/响应体，不用 print。

## 依赖、代码与非目标

Python >= 3.11，完整类型标注，非显然逻辑附清晰中文注释。
只增加当前任务确需的依赖，先检查标准库、现有库、维护状况、许可证与平台成本。
声明和 uv.lock 一起更新；运行时与开发依赖分开。

Ruff 负责 lint/format/import 排序，Pyright 负责类型，Pytest 负责测试。
不引入 Black/isort/flake8/Mypy/Loguru/Poetry 等重复主工具。
不重新包装 FastAPI、SQLAlchemy、Alembic、Pydantic 或 Celery。

v0.1 不扩展 Docker/Kubernetes、前端、完整 RBAC、菜单、部门、租户、工作流、
CRUD 生成器、通用 CRUD Service/Router、自动路由扫描、复杂 IoC、插件市场、
SSO/OAuth/OIDC 或监控平台。仅 auth/user/file 参考模块。
详情见 [coding-convention](docs/coding-convention.md)与 [roadmap](docs/roadmap.md)。

## 测试与质量命令

行为变更有相应测试；缺陷先复现，后修复。
按 unit/integration/api 分层；不 Mock 被测组件。
Repository 使用真实 SQLAlchemy，Local 使用临时文件系统，云 SDK 边界可模拟。
发布前必须验证三数据库迁移与核心集成；API 变更检查 OpenAPI。

先运行 `uv sync`，激活 .venv 后执行（或分别加 `uv run` 前缀）：

```bash
ruff check .
ruff format --check .
pyright
pytest
```

不删除测试、放宽断言或用 skip/xfail、广泛 ignore/noqa 掩盖问题。
测试隔离、覆盖要求见 [testing](docs/testing.md)。

## Definition of Done

- [ ] 仅当前任务范围，架构边界完整，无无关重构或多余依赖。
- [ ] 类型与中文说明完整，适用行为测试已更新。
- [ ] 模型迁移、API/OpenAPI、文档按变更同步。
- [ ] uv sync、Ruff lint/format、Pyright、适用 Pytest 全通过。
- [ ] 无秘密泄漏、默认凭据或运行数据入库。
- [ ] 完整审查差异，报告文件、决策、依赖、真实验证结果与未解决事项。
