# M0–M9 最终全量审计

审计日期：2026-09-13。范围为当前 `0.1.0.dev0` 的源码、迁移、依赖声明/锁文件、
unit/integration/api 测试、CLI/Worker 入口及全部项目文档。基线为 M9 已完成的交付。
本次按设计代码树归位、精简无实际基础设施职责的文件，并修复复现出的安全与并发问题。
不增加第四个业务模块、通用重试框架、权限平台或部署平台，不执行发布、打标签或生产操作。

## 结论与适用边界

当前实现符合 Template-first、Lightweight、Explicit、Modular、Replaceable、Predictable 的基座定位：
默认 SQLite/Local 可独立运行，业务与 HTTP/CLI/Worker 入口分离，资源作用域和业务事务归属明确，
可选能力通过显式配置与 Bootstrap 装配。已确认的问题见下表，均附回归或既有契约验证。

“可复用、面向生产”不等于已经验证任意负载或提供高可用 SLA。脚手架提供代码层的隔离、
错误语义、补偿与资源释放；多实例运行还要求共享 JWT 秘密、可被各实例访问的数据库/存储、
进程管理、HTTPS、入口限流与大小限制、备份恢复及目标平台验收。
SQLite 的单写者、Local 的单机文件位置、无状态 Token、跨系统补偿的限制需要明确保留。

## 发现与处置

| 编号 | 问题与证据 | 最终处置 | 回归证据 |
| --- | --- | --- | --- |
| A01 | Celery 文件名及 Redis/Celery 测试目录偏离设计；代码树仍以 M8 为说明时点 | `task.py → base.py`、`logging.py → signals.py`；测试归入 `integration/redis/`、`integration/celery/`；同步全部引用 | 原有 Worker、桥接、重试、上下文、Redis 生命周期测试保留；真实独立 Worker 复验 |
| A02 | NullTokenStore 仅返回 false/None，无 I/O、SDK 或资源职责，却独占 Infrastructure 文件 | 与 Protocol 合放 `providers/token_store.py`，删除旧文件；业务仍依赖 TokenStore，Bootstrap 注入默认空实现 | 无状态语义测试与独立解释器导入边界检查 |
| A03 | 两个真实 Bearer 请求同时创建不同用户，稳定复现 `[500, 201]` | 当前用户查询使用独立短 Session，在业务执行前释放认证读事务，返回已加载的脱管身份快照；必选/可选认证共用 | 不同用户名均 201；同名得到 201/409；真实权限链与文件 API 回归 |
| A04 | SQLite 并发更新/删除的读锁升级竞争被当成未知 500；连接池耗尽同样无法区分 | 中央处理器仅将 SQLite BUSY（含扩展码）、连接池超时、明确失效连接映射 503/11001；其他 SQL 故障仍为 500；同步 OpenAPI | 并发更新/删除得到明确竞争响应，释放后重试成功；真实单连接池耗尽与恢复 |
| A05 | 上传校验线程被阻塞时取消请求，Service 立即退出，入口提前关闭仍在读取的流 | shield 校验任务，等待线程完成后再传播取消；不继续上传和写元数据 | 慢流成功/失败两种结束路径均验证关闭顺序、取消传播及无新增文件/记录 |
| A06 | public/private 指向外部目录时 Local Adapter 拒绝使用，但 doctor 报告健康 | 诊断按 Local 相同路径规则拒绝符号链接及 Windows junction，保持只读 | 两个可见性目录的真实链接测试；原 CLI 只读与健康检查回归 |
| A07 | `access_key_id` 结构化字段和 `AWS_ACCESS_KEY_ID=...` 文本出现在实际日志输出 | 扩展云 Access Key 字段及带标签文本脱敏，保持递归处理及不修改调用者对象 | console/json、structlog/标准 logging 的真实输出均验证隐藏 |
| A08 | 签名有效但 iat/exp 为 Infinity 的 JWT 触发 PyJWT 整数转换 OverflowError | 与其他声明解析错误统一拒绝为 AuthenticationException/401 | iat/exp 非有限值回归；签名、算法、有效期、类型混用原有用例继续保留；此项不涉及签名绕过 |
| A09 | README/主题文档存在旧里程碑、预留 CacheProvider、未实现 SoftDeleteMixin 等容易误读为现有能力的文字 | 代码树列出实际交付，预留项单独说明；更新功能、事务、错误、安全、测试及发布文档 | 本地文档目标/锚点、旧导入引用和实际文件树核对 |

## 架构精简复核

按“当前职责、依赖方向、是否有实际调用方”判断，不以文件同名或行数作为唯一依据。

| 区域 | 决定 | 理由 |
| --- | --- | --- |
| TokenStore / NullTokenStore | 合放一个文件，保留两个类型 | Protocol 表达可替换能力；Null 表达无状态策略。合放不会带入外部依赖，也无需兼容转发文件 |
| StorageProvider 与三个 Adapter | 保留分离 | 有真实文件系统/SDK 行为、阻塞边界、安全路径及契约测试，是实际替换边界 |
| Bootstrap 注册文件 | 保留设计中的显式入口 | 应用、Worker、CLI 装配职责不同；注册位置明确，避免自动扫描或全局容器 |
| Settings 分组 | 保留 | 各组已有字段和独立校验，聚合处负责来源与跨组约束；不增加空配置组 |
| 异常描述符/类与 HTTP Handler | 保留边界 | 公共契约可脱离 FastAPI 导入，业务无需依赖响应实现；错误集中转换 |
| FileRepository 等薄模块类 | 保留参考模块入口 | 明确模型绑定和模块数据访问职责，继承现有最小 CRUD，不增加通用 Service/Router 层 |
| PageResult / Page、TokenPair / TokenResponse | 保留 | 应用结果与 API 序列化各有调用方和类型职责，ORM 不强制变成响应 DTO |
| metadata、diagnostics、Storage common | 保留 | 分别承担显式迁移注册、只读运维、安全键名和 SDK 阻塞调用，均有实际使用 |
| Cache/Mail/HTTP、Auth 专属错误、File Task 等预留项 | 不创建 | 当前没有所需业务调用方；未用枚举/工具合集、默认撤销存储或空任务不为对齐目录而加入 |

实现文件清单、移动映射和保留差异以 [Project Structure](Project%20Structure.md) 为准。
无数据库模型或迁移变更；无运行时/开发依赖新增，`pyproject.toml` 与 `uv.lock` 保持不变。
新增非显然逻辑有中文说明，严格类型检查和 Ruff 继续作为质量门。

## 安全与并发覆盖

| 主题 | 已检查的保证 | 明确不承诺的部分 |
| --- | --- | --- |
| 认证 | Argon2id、随机盐、未知账号虚拟哈希；固定 HS256、必需声明及严格类型；每请求重查用户状态 | 默认无登录限流或多因素认证；部署入口需控制请求速率与并发资源 |
| 授权 | 用户管理需超级管理员；Schema 禁止批量修改密码/权限；Service 自删规则；文件所有权、匿名/他人/管理员、孤儿文件 | 无完整 RBAC、租户、数据范围或审计平台；身份是本次鉴权时点的快照 |
| 秘密与日志 | 配置安全默认值、生产 fail fast；密码/Token/云密钥/连接 URL 脱敏；错误不返回 SQL、SDK 文本或 traceback | 自定义业务不能将无标签秘密当普通事件文本记录；配置秘密仍需部署环境妥善管理 |
| 输入与文件 | Pydantic 字段约束、参数化 SQL、实际流大小校验、安全 UUID key、链接拒绝、私有文件不静态挂载、attachment/no-store/nosniff | 扩展名/MIME 不是内容扫描；框架暂存前的请求大小需入口限制；Local 根目录不能交给不可信本地写入者 |
| 并发与事务 | Session 不跨请求/任务共享，身份读事务提前释放；唯一约束兜底；请求/任务上下文隔离；连接池和明确锁竞争 503 | SQLite 不提供高并发写入能力；无乐观版本字段、ETag/If-Match 或通用幂等键，不承诺冲突更新检测 |
| 失败与取消 | Service 事务回滚，入口关闭资源；存储线程结束后关闭上传流；上传补偿与删除部分失败有安全日志 | 数据库和对象存储非原子；硬终止、网络超时、补偿失败后须核对对象与元数据，不能盲目重放写请求 |
| JWT 状态 | TokenStore 可替换，默认 Null 模式语义与文档一致 | 退出不即时撤销，旧 refresh 可重用；启用 Redis 不自动改变此行为 |
| Worker | JSON、有限暂时故障重试、独立桥接/Session、上下文恢复、真实 Broker/进程路径 | Windows solo 不证明 Linux prefork 或硬/软超时；新增写任务需独立设计幂等与提交后发送 |
| 部署与恢复 | 干净模板安装/显式迁移/CLI 初始化/真实 HTTP 验收；三数据库临时实例验证 | 未做长期压力测试、故障转移或备份恢复演练；`/health` 仅表示进程存活 |

本次审计基线无 CORS 或通用安全头平台；后续上线收口已补充默认关闭的明确来源 CORS，
见 [新旧脚手架收口](scaffold-review.md)。Cookie 认证、跨域凭据、SSO 等能力仍须按实际业务重新评估。
本次源码审计与行为测试不等于第三方渗透测试，也不等于对全部第三方依赖漏洞的认证。

## 本次验证记录

环境：Windows、Python 3.13.15；依赖使用当前锁文件。普通测试使用临时 SQLite，
外部矩阵各自创建独立数据目录、随机密码、回环监听和临时端口；未连接已有业务库。
外部服务测试结束关闭进程、清理专用测试资源；本次下载的数据库二进制已清理，
临时审计辅助脚本与结果记录位于忽略缓存中，不进入交付源码或项目依赖。

质量检查使用 `.venv/Scripts/` 中的工具；当前终端未将 uv 加入 PATH，
uv 缓存显式放在允许写入的临时/项目缓存目录。最终结果如下：

| 检查 | 结果 |
| --- | --- |
| uv sync / 锁文件 | 已通过；无依赖声明或锁文件变更 |
| Ruff lint / format | 通过，137 个 Python 文件格式检查通过 |
| Pyright strict | 0 errors、0 warnings |
| Pytest / coverage run | 380 passed，无 skip/xfail；修复前基线 369 passed |
| 语句与分支综合覆盖率 | 整体 95.31%；Core 98.52%；Security 100.00%；Database 92.81%，均达到门槛 |
| OpenAPI / 导入边界 | 全量测试通过；公共 503 契约已同步，旧模块导入无残留 |
| 文档 / 目录 / 差异 | 22 份 Markdown、102 个本地链接/锚点、156 个源码/文档树条目核对通过；4 处移动保留运行逻辑/测试主体；diff whitespace 检查通过 |
| PostgreSQL 17.11 / asyncpg 0.31.0 | 4 passed；迁移升级/check/降级/再升级、Repository/Auth/User/File |
| MySQL 8.0.46 / asyncmy 0.2.14 | 4 passed；同一在线发布测试，专用空库 |
| 真实 Redis 7.4.11 + 独立 Celery Worker | 1 passed；任务结果、永久失败、关联上下文及清理 |
| 干净模板 | locked/no-dev 安装、可选包缺席、CLI 迁移/管理员/doctor、真实 Uvicorn 私有文件流程通过 |
| 真实 HTTP 并发 | 12 个客户端线程执行 48 次 Bearer 读取：48/48 成功且请求 ID 隔离；6 个并发创建：6/6 成功 |

HTTP 并发检查是功能与资源隔离验收，不是吞吐、容量或长期压力基准，不据此给出 QPS/SLA 承诺。

可复制质量命令见 [testing](testing.md#发布质量)，三数据库命令及安全空库要求见
[release](release.md#三数据库在线验证)，真实 Worker 入口见 [celery](celery.md#上下文与测试)。
原 M9 验证记录保留在 release；本页是最终审计增量，不能将历史通过或未运行项计为本次通过。

## 正式发布仍需完成

- 使用 OSS/COS 时，在专用测试桶与最小权限凭据下执行真实 ACL、签名、上传/下载/删除验收；本次只验证 Adapter 契约。
- 对目标 Python/操作系统/数据库版本重跑测试；Python 3.11 最低声明通过静态目标检查，本次实机为 3.13.15。
- 多实例与持续并发写入使用适当数据库和共享存储；按业务负载配置入口并发/限流、连接容量及恢复方案，执行实际压力和故障演练。
- LICENSE 当前年份为 2026，版权主体仍需填写；确认正式版本号、发布清单和标签，当前仍为开发版。

## 实现依据

修改时通过 Context7 核对 Celery 基类/信号、SQLAlchemy Session 生命周期和 Python asyncio 取消语义。
可参考 [SQLAlchemy Session.close](https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.Session.close)、
[Python shield](https://docs.python.org/3/library/asyncio-task.html#shielding-from-cancellation)
与 [Celery signals](https://docs.celeryq.dev/en/stable/userguide/signals.html)。
PostgreSQL 使用 [官方 Windows 页面推荐的二进制来源](https://www.postgresql.org/download/windows/)，
按 [initdb](https://www.postgresql.org/docs/17/app-initdb.html) 初始化临时集群；
MySQL 隔离初始化依据 [官方数据目录说明](https://dev.mysql.com/doc/refman/8.0/en/data-directory-initialization.html)。
