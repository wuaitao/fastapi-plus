# 变更记录

## [Unreleased] — 0.1.0.dev0 / M9 Release Hardening

- 对照原 fastapi-scaff 补齐默认关闭的明确来源 CORS，覆盖预检、错误响应、请求 ID 与下载文件名响应头。
- 将未知异常兜底移到 CORS 内层，上下文留在外层；保持安全错误、日志及流式中止语义。
- 支持配置 OpenAPI 名称、简介和说明，版本改用已安装项目元数据，与 CLI 保持一致。
- 固定 Git 检出的 Python 文件为 LF，与 Ruff 一致，修复 Windows 换行符造成的格式检查失败。
- 新旧项目取舍和本次验证见 [上线收口](docs/scaffold-review.md)；无新增依赖或数据库迁移。
- 最终审计按设计将 Celery 基类/信号归位为 `base.py`/`signals.py`，Redis/Celery 集成测试归入独立目录，同步导入与文档。
- 合并 TokenStore 契约与默认空实现，删除没有 I/O 或资源职责的独立 `infrastructure/token_store.py`。
- 修复认证查询与业务写入共享 Session 导致 SQLite 并发创建返回 500；身份查询结束即释放独立读事务。
- 明确的数据库锁竞争、连接池耗尽与失效连接映射安全 503，保留其他 SQL 故障的 500 语义并同步 OpenAPI。
- 补齐云 Access Key ID 结构化字段及带标签文本的日志脱敏。
- 将 JWT 非有限时间声明引起的整数转换溢出统一作为无效令牌拒绝。
- 修复取消上传校验时入口提前关闭线程仍在读取的流；修复 doctor 将存储可见性目录链接误报为健康。
- 增加并发创建/冲突、取消生命周期及存储诊断回归；完整复核见 [全量审计](docs/audit.md)。
- 新增默认 SQLite、显式 PostgreSQL/MySQL 共用的在线发布测试：Alembic 升级、模型检查、
  降级和再升级，Repository 回滚、分页、UTC、并发用户名/邮箱唯一冲突，以及完整 Auth/User/File 流程。
- 新增完整 OpenAPI 引用和 operationId 检查、统一错误/响应模型验证；补齐两个文件接口的描述。
- 补充 Repository/Router 架构边界保护；保留公共契约、Service、CLI 的独立导入检查。
- 增加仅用于开发的 coverage.py，整体门槛 80%，Core/Security/Database 各 90%。
- 完善 README、贡献指南、主题文档和发布清单，修正 Redis/TokenStore 与旧里程碑状态说明。
- 未改变业务 API 路径、数据库模型/迁移或默认安装能力；未引入 Docker、前端或新业务模块。

实际数据库版本、质量结果与限制见 [M9 发布验收](docs/release.md)。本条目不代表 0.1.0 已发布。

## M0–M8 开发基线

- 应用工厂、类型化配置、结构化日志、请求 ID、统一 JSON 响应与异常。
- SQLAlchemy async、Alembic users/files 迁移、User 管理、Argon2id 和 JWT 认证。
- File 与 Local/OSS/COS Provider、可选 Redis/Celery、独立 Worker 和用户状态示例任务。
- Typer CLI：version、doctor、db、交互创建管理员；不提供默认凭据或启动自动迁移。
