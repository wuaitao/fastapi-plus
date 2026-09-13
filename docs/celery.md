# Celery 与异步任务

M7 已实现可选 Redis/Celery、独立 Worker、集中异步桥接及唯一任务 `user.status`。

## 安装与启动

默认部署 `uv sync --no-dev` 不安装 Redis/Celery；只启用应用 Redis 客户端时使用
`uv sync --no-dev --extra redis`，启用任务时使用 `uv sync --no-dev --extra celery`。
开发组包含 Celery/Redis 和 celery-types，以便默认质量命令执行真实任务测试。
运行时仍默认关闭，不要求外部服务。锁定 Redis 6.4（MIT）、Celery 5.6（BSD-3-Clause），
类型桩仅供开发（Apache-2.0）；未增加核心运行时依赖。

按需设置环境变量或本地 `.env`，不要提交真实服务凭据：

```dotenv
CELERY_ENABLED=true
CELERY_BROKER_URL=redis://localhost:6379/1
# 可选，不配置时任务执行但不保存结果。
CELERY_RESULT_BACKEND=redis://localhost:6379/2
# 独立的 Web Redis 客户端；任务 Broker 不要求开启此开关。
REDIS_ENABLED=false
```

使用显式迁移后的同一个 DATABASE_URL，另开进程启动 Worker：

```bash
uv run celery -A app.bootstrap.worker:celery_app worker --loglevel=INFO
```

Linux 部署采用 Celery 默认 prefork；Windows 本地验证使用 `--pool=solo --concurrency=1`。
solo 不提供 prefork 的软/硬任务超时保障，不作为该保障的生产验收。
未启用时 `celery_app` 为 None；Worker 命令要求先启用 Celery。

唯一示例只接受已提交的用户 ID，复用 UserService 读取状态，无写入副作用：

```python
from app.bootstrap.worker import celery_app

assert celery_app is not None
result = celery_app.tasks["user.status"].apply_async(
    args=(1,), headers={"correlation_id": "example-request"}
)
# 仅在配置结果后端时，独立同步脚本可调用 result.get(timeout=10)。
# Web 请求不要阻塞等待 Worker；文件上传不会触发该任务。
```

结果为 `{"user_id": 1, "is_active": true}`。未知用户、非法 ID 不重试；
只对 SQLAlchemy TimeoutError 或已标记 connection_invalidated 的数据库故障重试，
最多 3 次（总计 4 次尝试），原生指数退避带 jitter，上限 60 秒。
默认软/硬超时为 30/60 秒；任务运行时创建资源，不在导入或父进程预建数据库连接。

## 可选运行时

Celery 默认关闭（CELERY_ENABLED=false），Redis 同样默认关闭。
Web、Worker、Beat 是独立进程；Web 启动不能顺带启动 Worker/Beat。

Celery 使用原生任务能力，基础设施目录负责应用实例、配置、日志与桥接，
bootstrap/worker 负责 Worker 装配。任务包装靠近业务模块。
基类与有限重试位于 `infrastructure/celery/base.py`，发送上下文及 Worker 日志信号位于
`infrastructure/celery/signals.py`，与设计代码树一致。
Worker 不导入 FastAPI 全局应用、不使用 Request、Depends 或 app.state。

启用时可以使用 Redis Broker，结果后端按需配置；
默认队列保持简单，不构造复杂队列拓扑或动态调度平台。

## 任务边界

```text
Task Wrapper → 集中 Async Bridge → Async Handler / Service → Repository / Provider
```

Task 仅处理参数、上下文、Service 调用、重试与结果；
业务不堆在 Task 或 Celery Signal 中。
集中桥接位于 infrastructure/celery/bridge.py，
统一事件循环和资源策略，不在每个 Task 中调用 asyncio.run。

每个任务拥有独立 Session 作用域，Worker 自建进程资源；
Service commit/rollback，任务结束关闭 Session。
当前桥接使用标准库 asyncio.Runner，每次尝试创建独立循环、NullPool Engine 和 Session；
退出关闭 Session、释放 Engine，随后关闭循环。桥接不隐式提交，失败和未提交事务自动回滚。
不得跨进程/事件循环共享 Web Engine 连接、Session 或 HTTP 客户端。

参数与结果只使用简单 JSON 可序列化数据，优先传业务 ID。
禁止传 ORM、UploadFile、Session、Request、Provider 或完整 Token。
JSON 为默认序列化方式，不开启 pickle。任务名显式采用 module.action。

## 重试与业务一致性

任务按可能重复执行设计，用业务状态或数据库约束保障幂等。
只对明确的暂时性失败重试，使用有上限的 backoff/jitter；
用户不存在、权限失败、非法文件等永久错误不反复重试。
按任务性质设置超时，不使用无限重试。

依赖已提交记录的任务在业务提交后发送；数据库和 Broker 不具有原子事务。
Broker 提交失败不能声称任务已接受，HTTP 映射为安全的基础设施错误。

task_id 是执行标识，不代替业务 job_id。
v0.1 不增加通用 Job 表、任务状态 API、进度平台、取消引擎或 DLQ；
具体业务以后按需管理状态。

## 上下文与测试

Task headers 传 correlation_id、actor_id 等上下文，参数保留业务含义。
绑定 task_id、task_name、retry_count、duration_ms，任务结束清理上下文。
不记录敏感任务参数。
发送信号自动将 structlog 的 request_id/correlation_id、actor_id 传入消息头，显式头优先。
Celery 将 correlation_id 视为保留字段，因此发送边界同步保存 x_correlation_id，Worker 从该头恢复。
Worker 的 setup_logging 信号接入现有 structlog；BaseTask 记录安全的完成/失败事件。
Celery/Kombu 原生任务日志可能拼接参数、结果及底层异常，Worker 禁止其传播到输出；
发送时也隐藏 argsrepr/kwargsrepr。安全任务事件仅含上下文、耗时、结果状态与异常类型。

M7 只增加一个小示例以验证 Wrapper/Handler 结构，
默认文件上传不触发 Worker。验证禁用导入、序列化、Handler、
重试、Session、关联 ID 和上下文清理。
Eager 模式仅用于快速检查，不能替代少量真实 Broker/Worker 关键路径验证。

默认 `uv run pytest` 验证缺失依赖时的完整应用启动、配置、Redis 生命周期、真实 SQLite
Handler/事务、JSON、有限重试、上下文清理，以及 memory Broker 上的非 eager solo Worker。
对应集成测试位于 `tests/integration/redis/test_client.py` 和 `tests/integration/celery/test_worker.py`。
真实 Redis + 独立 Worker 验证为显式入口，不进入默认测试收集：

```bash
# redis-server 在 PATH 中时无需额外配置；否则设置 REDIS_SERVER_EXECUTABLE 的绝对路径。
uv run pytest tests/manual_optional_infrastructure.py -q
```

该用例自行启动回环地址、临时端口、无持久化的 Redis 和独立 solo Worker，
使用临时 SQLite 验证入队、结果返回、永久错误、correlation_id 与后续任务上下文清理；
不连接已有 Redis，不读取开发者配置。Windows 同样隐藏启动测试进程。
