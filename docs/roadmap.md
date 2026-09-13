# 产品范围与路线图

## 产品契约

FastAPI Plus 是 **Template-first** 的轻量、面向生产的 FastAPI 后端 Starter。
架构坚持 **Lightweight / Explicit / Modular / Replaceable / Predictable**。

> Secure by default. Extensible by design. Minimal in core. Explicit is better than magic.

v0.1 的目标是提供可直接开始真实业务开发的后端基础，
不是完整 Admin、低代码平台或独立重型框架包。

## v0.1 必需能力

- Python >= 3.11；FastAPI 应用工厂、类型化配置、结构化日志、请求 ID。
- 中央异常转换、统一 JSON 业务响应、正确 HTTP 语义与 OpenAPI。
- SQLAlchemy 2.x async、Alembic；默认 SQLite，实际验证 MySQL/PostgreSQL 支持。
- 数据库生成 integer/BIGINT 风格主键，API 按精度需求字符串化；不使用默认 Snowflake。
- auth/user/file 参考模块；Argon2id、JWT access/refresh、HTTP Bearer。
- 默认 Local 存储；完整 Aliyun OSS、Tencent COS Adapter。
- Redis 与 Celery 可选、默认关闭；独立 Worker、集中异步桥接。
- 当前项目 CLI、测试与文档；无默认管理员凭据。

默认完整运行体验仅依赖 Python、SQLite 和本地文件系统。
云账号、Redis、Worker 和外部数据库仅在选择相应能力时需要。

## 非目标

v0.1 不要求 Docker、Kubernetes、前端代码或 Admin UI。
不包含完整 RBAC、角色/权限关系管理、菜单、部门、租户、数据范围、
工作流、低代码 CRUD、通用 Service/Router 框架、插件市场、
自动路由扫描、复杂 IoC、Event Bus、SSO/OAuth/OIDC、
验证码、邮件平台、完整审计、Prometheus/Sentry/OpenTelemetry。

生成器、更多 Provider 或上层业务可以未来评估，不是当前交付承诺。
不为未来扩展预装依赖或创建大量空类。

## 里程碑

M0–M10 共 11 个阶段；每个阶段须通过适用质量门，单独授权后才继续下一阶段。

| 阶段 | 交付 | 验证重点 | 状态 |
| --- | --- | --- | --- |
| M0 | 仓库、15 份主题文档、规则、元数据、工具链、最小测试 | uv sync、Ruff lint/format、Pyright、Pytest、完整差异审查 | 已完成 |
| M1 | Bootstrap、Settings、应用工厂、Lifespan 骨架、GET /health | 默认/非法配置、应用创建、Health、OpenAPI | 已完成 |
| M2 | structlog、请求 ID、响应、分页、错误描述符和中央 Handler | 422/404/405/500、请求 ID、脱敏、OpenAPI 契约 | 已完成 |
| M3 | SQLAlchemy async、Session、Base、时间字段、最小 Repository、Alembic 环境 | SQLite、资源释放、分页、回滚与迁移接线 | 已完成 |
| M4 | User Model/Schema/Repository/Service/Router、密码哈希、users 迁移 | CRUD、唯一约束及并发冲突、分页、错误 | 已完成 |
| M5 | JWT/Auth、当前用户、基本权限 hook | 登录/刷新/退出语义、Token 安全、禁用用户、401/403、自删规则 | 已完成 |
| M6 | Storage 契约/Registry、Local、File、files 迁移、OSS/COS | 私有访问、流、安全路径、补偿、可选导入与契约测试 | 已完成 |
| M7 | 可选 Redis/Celery、独立 Worker、异步桥接、小型任务示例 | 默认关闭、序列化、重试、Session、correlation_id、真实关键路径 | 已完成 |
| M8 | 项目 CLI：version/doctor/db/create-superuser；开发运行沿用 Uvicorn | 只读诊断、命令映射、退出码、复用 Service | 已完成 |
| M9 | Release Hardening：兼容性、测试、完整文档与安全复查 | 三数据库迁移/核心集成、OpenAPI、类型、覆盖率、架构与启动验收 | 已完成（当前交付，结果见 release） |
| M10 | 正式发布验收 | 版权信息、按需真实云验收、版本与发布清单确认 | 待维护者确认 |

本次 M9 按授权任务将原 M10 的文档与发布加固工作合并；不新增业务能力、不自动发布。
实际验证环境、命令和仍需维护者处理的事项见 [发布验收](release.md)。

M0 不实现应用工厂、Health、配置系统、日志运行时、中间件、异常系统、
数据库 Engine、BaseRepository、迁移运行时、业务模块、Provider、CLI 或任务。
占位文件不能被描述为后续功能已经完成。

M0–M9 完成后已按 [Project Structure](Project%20Structure.md) 复核代码树并完成最终审计，
包括 Celery 基类/信号文件与 Redis/Celery 测试归位、引用核对及文档同步。
API 路径、配置名称、数据库模型和迁移保持不变；可靠性修复与真实验证结果见
[全量审计](audit.md)。必要辅助文件与不创建的预留项在代码树文档中明确列出。

## v0.1 发布门槛

- [x] 干净模板副本按 README 可完成依赖同步、显式迁移、显式管理员创建和开发启动。
- [x] SQLite 默认 Auth/User/File 流程不依赖 Redis、云服务或 Worker。
- [x] SQLite、MySQL、PostgreSQL 均通过空库迁移、核心 Repository 与参考模块集成。
- [ ] Local 真实文件系统及 OSS/COS Adapter 契约通过；保留专门凭据的真实云验证。
- [x] 可选组件未安装且未启用不影响核心，已启用失败给出明确提示。
- [x] 密码、Token、禁用用户、401/403、私有文件、配置和日志安全测试通过。
- [x] JSON 错误无 detail 泄漏，OpenAPI 与实际响应及 Bearer 安全一致。
- [x] CLI 运维命令可用，doctor 只读，不存在默认凭据或启动自动迁移。
- [x] Ruff lint/format、Pyright、Pytest 全部通过；覆盖率目标见 testing。
- [ ] README、主题文档、AGENTS、贡献指南、许可证与实际实现一致。

首个正式版本为 0.1.0，当前包元数据保留 0.1.0.dev0。
M9 加固完成不代表已发布；未勾选项须在正式发布前处理。

## M0 文档归一化记录

| 早期草稿 | 当前统一决定 |
| --- | --- |
| 独立框架包、生成器先行 | Template-first；new/make 延后，M8 仅当前项目 CLI |
| BIGINT + Snowflake、可配置 ID 生成器 | 数据库生成整数，API Schema 处理精度 |
| Black/Ruff/Mypy 并用 | Ruff lint/format/import 排序，Pyright，Pytest，uv |
| 所有依赖集中 core/dependencies | 模块依赖留模块，跨领域资源单独装配 |
| Service 输出 API Schema | Repository → ORM，Service → ORM/应用结果，Router → Schema |
| 默认 Role/Permission、菜单或前端适配接口 | 仅认证、is_superuser、permission hook；无前端绑定 |
| DELETE 204 同时返回 JSON、验证错误 400 | 默认 DELETE 200 + envelope，Schema 验证 422 |
| /files/upload、/users/me 等并行入口 | /files 创建资源，/auth/me 获取当前用户 |
| 全局容器/任务目录及动态注册建议 | bootstrap 显式装配，任务靠近模块，集中 bridge |
| 文件复杂状态机、持久化 URL | 简化补偿流程，backend + key，默认私有 |
| 同时安装全部基础设施 | 各能力按阶段按需加入；Redis/Celery 默认关闭 |
| JSON 自动映射 JSONB、统一所有数据库参数 | 显式处理方言差异，并用真实矩阵验证 |
| users/files 一次性迁移、M0–M10 称 10 阶段 | 按 M4/M6 模型分步迁移，共 11 阶段 |
| MIT 仅为草稿倾向 | M0 已由维护者确认 MIT；年份已填为 2026，版权主体待填写 |

原设计草稿的有效要求已按主题合并，取代会话式原稿。
架构和目录材料归入 architecture；依赖政策归入 coding-convention；
产品范围、实施计划和发布验收归入本文。
