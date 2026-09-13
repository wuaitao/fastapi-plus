# 数据库

M3 已实现 `app/database/`、应用资源装配、请求 Session 依赖和 Alembic async 环境。
M4 已加入 users 模型及 `0001_create_users` 迁移；files 在 M6 加入。

## 选型与默认值

| 数据库 | 定位 | 驱动 |
| --- | --- | --- |
| SQLite | 默认，本地快速启动 | aiosqlite |
| MySQL 8+ | 支持；M9 实测 8.0.46 | asyncmy |
| PostgreSQL | 支持；M9 实测 17.11 | asyncpg |

采用 SQLAlchemy 2.x typed declarative、AsyncEngine、AsyncSession 和 Alembic。
直接使用框架的查询与映射能力，不创建自己的 ORM。
数据库连接由配置层提供；不在源码或文档示例中保存真实连接凭据。

默认 `DATABASE=sqlite`、`DATABASE_URL=sqlite+aiosqlite:///./data/app.db`。
相对路径基于工作目录，文件所在目录需已存在；仓库已保留 `data/`。
连接按首次数据库操作创建；应用导入、启动和 Health 不连接数据库，也不建表。
URL 使用 SecretStr 保存，配置校验要求后端和异步驱动匹配，不输出原始连接串。

```bash
uv sync                         # SQLite 核心依赖
uv sync --extra postgresql      # asyncpg
uv sync --extra mysql           # asyncmy
```

外部数据库同时设置 `DATABASE=postgresql` / `mysql`，以及由环境注入的
`postgresql+asyncpg://...` / `mysql+asyncmy://...` 连接串，必须包含主机和数据库名。
引擎关闭 SQL echo、隐藏绑定参数，启用连接存活检查和 1800 秒连接回收。
SQLite 显式启用外键约束与事务 BEGIN，使 DDL 和 SAVEPOINT 也能正确回滚。

## 模型与标识符

默认主键为数据库生成的 integer/BIGINT 风格整数，不使用 Snowflake，
不添加分布式 ID 生成器或运行时 ID 策略开关。
跨数据库映射须保留 SQLite 的整数主键自动生成能力，并在真实迁移中验证。
需要其他 ID 的业务可自行显式设计；API 精度边界见 [api](api.md)。

时间使用 UTC，命名 `created_at`、`updated_at`。
`TimestampMixin` 使用 `UTCDateTime`：写入要求带时区，数据库保存无时区 UTC，
读取恢复 UTC 时区。默认值和更新时间由 SQLAlchemy 维护，原始 SQL 写入者须显式维护。
MySQL 默认 DATETIME 精度为秒，不保证跨库保留微秒。
字符串长度、nullable、默认值与约束应显式表达。
关键 unique、foreign key、check、index 使用有意义的名称，
如 `uq_users_username` 和 `uq_users_email`。

数据库唯一约束保障并发正确性，提前查询只能改善错误提示。
默认物理删除；当前未提供 SoftDeleteMixin，业务需要软删除时自行显式设计。
审计字段同样按业务需要增加，不建立默认审计平台。

## 查询与事务

Repository 负责 SQL 查询、add、flush、refresh，返回 ORM，不 commit。
Service 定义完整业务事务并 commit/rollback；Web/CLI/Task 入口负责独立 Session 生命周期。
Session 不得全局共享，也不跨并发任务复用。

异步查询显式加载所需数据，避免隐式关系加载和 N+1。
查询、过滤、排序字段有明确白名单；分页契约见 [api](api.md)。
最小 BaseRepository 可以复用基本 CRUD/分页，但不加入通用 filter DSL、动态关联或 Service 工厂。

`BaseRepository(session, Model)` 提供 `get(id)`、`create(instance)`、
`update(instance)`、`delete(instance)`、`list(offset=0, limit=20)` 和
`paginate(page=1, size=20)`。更新前由模块明确修改当前 Session 内对象的允许字段；
创建/更新执行 flush 和 refresh，删除执行 flush，均不 commit 或 rollback。
列表固定按主键升序，limit/size 范围为 1–100；分页返回包含 ORM 对象的
`PageResult(items, total, page, size)`，由 Router 转为公开 `Page[Schema]`。
两种分页类型均定义在 `app/common/pagination.py`；应用结果不绑定 SQLAlchemy 类型。
业务过滤和排序在模块 Repository 中使用原生 SQLAlchemy 显式实现。

Bootstrap 在 Lifespan 中创建独立 Engine 和 session factory，并在关闭或异常退出时 dispose。
Web 使用 `app.database.session.get_session`；CLI/Task 可独立调用
`create_engine(settings)`、`create_session_factory(engine)` 和 `session_scope(factory)`。
Session 设置 `expire_on_commit=False`、`autoflush=False`；入口退出关闭 Session，
未提交事务会回滚，正常退出不会隐式提交。CLI/Task 还须在入口 finally 中 dispose Engine。

HTTP 当前用户查询使用独立短 Session，并在业务入口执行前关闭；返回的 User 为已加载的脱管快照。
登录、刷新和退出仍由请求级 AuthService 处理，业务写入由各自 Service 管理事务。
这避免认证 SELECT 与并发创建共用事务时，SQLite 将读锁升级为写锁而返回 500。
SQLite 本身仍只有单写者，业务先读后写的竞争不具备服务器数据库的行锁能力；
持续并发写入与多实例部署应选择经过目标环境验证的 PostgreSQL/MySQL。
明确的 SQLite BUSY、连接池耗尽和已失效连接返回安全 503；其他未知数据库故障仍为 500。
并发更新/删除测试验证锁竞争响应及释放后显式重试的恢复，不承诺 SQLite 所有并行写入都成功。

并发唯一冲突在了解业务与具体约束的边界转换，失败事务由 Service 回滚。
不能将所有 IntegrityError 映射为“用户已存在”，也不能返回底层 SQL/约束细节。

## 迁移与兼容性

M3 加入 Alembic async 环境、metadata 接线和迁移模板；
M4/M6 随 users/files 模型分别提交迁移。变更模型时人工检查生成的迁移。

在 `app/database/metadata.py` 显式导入新增模型，迁移环境读取同一份 `Base.metadata`。
不扫描目录，不导入全局 Web app。配置只来自 Settings，不读取 ini 中的连接串。
INI 保持 ASCII 以兼容 Windows 本地编码，中文操作说明放在 Python 源码和本文中。
迁移模板已导入 UTC 自定义类型；SQLite 自动生成启用 batch 模式。

```bash
uv run alembic revision --autogenerate -m "describe schema change"
# 人工审查生成的迁移后执行
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade -1
```

当前 `upgrade head` 创建 users、files 与 Alembic 版本表，不创建业务数据。
users 包含数据库生成的整数主键、具名 username/email 唯一约束及 UTC 时间字段；
迁移可降级至 base 后重新升级，并通过 `alembic check` 检查模型一致性。
`upgrade head --sql` 可输出离线 SQL；SQLite 涉及表重建的 batch 迁移应在线执行。

应用启动不自动 migrate 或建表，生产不使用 create_all。
迁移是独立、显式的操作；测试建表不能代替迁移验收。

优先使用通用 SQLAlchemy 类型与查询，不假设 JSON 会自动变为 PostgreSQL JSONB。
跨数据库差异需显式映射和验证，不通过隐藏方言差异的自造 ORM 解决。

发布前 SQLite、MySQL、PostgreSQL 都必须通过空库迁移、核心 Repository、
唯一约束、分页与参考模块集成测试。测试只操作独立测试数据库，详见 [testing](testing.md)。

M9 在 SQLite 3.50.4、PostgreSQL 17.11、MySQL 8.0.46 上执行同一套在线发布测试，
验证空库迁移/检查/降级/再升级、自动主键、UTC、分页、回滚、并发用户名与邮箱唯一冲突，
以及认证、权限、Local 文件流程和删除所有者后的外键置空。
运行方法和准确平台范围见 [发布验收](release.md#三数据库在线验证)。
服务器版本或数据库排序规则变化后须重跑；不以离线 SQL 编译代替在线兼容性结论。
用户名和邮箱的大小写比较采用所选数据库的排序规则，当前未强制跨库统一大小写语义。
