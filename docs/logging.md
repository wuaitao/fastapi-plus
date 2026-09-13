# 日志

M2 已实现日志运行时和 HTTP 上下文，Celery 上下文在 M7 接入。

实现位于 `app/core/logging/`：`config.py` 配置输出，`redaction.py` 脱敏及提取
安全异常诊断，`context.py` 提供请求上下文中间件。应用工厂配置日志，
`bootstrap/middleware.py` 集中注册中间件。
`LOG_FORMAT` 可选 console/json；未设置时开发/测试为 console，生产为 JSON。
`LOG_LEVEL` 默认为 INFO，支持 DEBUG/INFO/WARNING/ERROR/CRITICAL，输出到 stderr。
配置属于进程级状态，同一进程再次创建应用时最后一次日志配置生效。

## 结构化事件

唯一主日志库为 structlog，与标准 logging 集成。
Bootstrap 配置日志，业务模块仅获取 logger，不自行配置输出或包装新日志框架。

事件名稳定采用 resource.action，如 user.created、request.completed、task.failed。
字段表达上下文，不用 print 或 f-string 长句作为主要日志结构。
开发输出可读 console，生产输出 JSON；时间 UTC ISO 8601，耗时统一 duration_ms。

| 字段 | 含义 |
| --- | --- |
| request_id | 单次 HTTP 请求 |
| correlation_id | 跨 HTTP、Worker 等边界的调用关联 |
| actor_id | 操作者标识 |
| task_id、task_name | Celery 执行上下文 |
| duration_ms | 请求或任务耗时 |
| method、path、status_code | HTTP 完成事件 |

应用启动/关闭事件可记录版本、环境、数据库方言与能力启用状态，不记录秘密配置。

## 上下文

合法、可信格式的 X-Request-ID 可复用，否则服务端生成；
响应头返回该标识，包含 500 错误路径。
通过 contextvars 绑定请求上下文，业务层无需接触 Request。

仅复用单个头中匹配 `[A-Za-z0-9_-]{1,64}` 的值；缺失、重复、过长或非法时
生成 UUID4 十六进制字符串。此值仅用于关联，不作为认证或可信身份凭据。
请求 ID 同时可从 `request.state.request_id` 读取；每次请求开始清空旧字段，
结束后恢复调用方上下文，避免串入后续请求。

HTTP 提交任务时用 correlation_id 关联请求；Worker 另有 task_id，
不把任务执行冒充新的 HTTP request_id。
每次请求/任务结束清理上下文，测试必须覆盖并发隔离与复用进程。

## 输出与脱敏

默认每个请求记录一次完成事件，包含成功/失败状态与耗时。
协调 Uvicorn/Celery 原生日志，避免重复访问和异常日志。
Repository 普通查询不逐条 INFO，生产默认禁用 SQL echo。

敏感字段匹配不区分大小写，脱敏 password、password_hash、Token、
Authorization、Cookie、各类 secret 及含凭据连接 URL；需要处理嵌套结构。
Access Key / AccessKeyId / AWS_ACCESS_KEY_ID 等云凭据字段及带标签文本同样脱敏。
签名下载 URL 同样视为敏感，不记录。
默认不记录完整 query、请求体、响应体、文件内容或多余个人信息。
异常诊断也必须遵守脱敏，不把敏感值藏进异常文本或 traceback 局部变量。

已知业务异常在有语义的边界记录，通常不输出 traceback；
未知异常由集中安全兜底记录一次安全内部诊断，对外遵循 [errors](errors.md)。
不在 Repository、Service、Router、Handler 各重复记录同一错误。

上下文层位于 CORS 外层，启用跨域后的 OPTIONS 预检也记录完成事件和请求 ID；
未知异常兜底位于 CORS 内层，使安全错误响应经过跨域头处理。装配顺序见 [configuration](configuration.md)。

未知异常的 `request.failed` 仅记录 `error_type` 和函数名/行号组成的 `frames`，
不记录异常文本、源码或局部变量。通用输出处理器移除 exc_info/stack 等原始诊断，
并隐藏未知对象，避免 repr 泄漏。含用户信息或查询参数的完整 URL 整体脱敏。
业务日志仍须遵守固定事件名与结构化字段约定，不能把秘密作为无标签自由文本记录。
禁用 Uvicorn 原生访问日志；标准日志经过同一脱敏 Formatter。
输出流故障时禁用标准 logging 的原始记录/traceback 调试回退。

## 级别与验收

DEBUG 为诊断细节，INFO 为正常重要事件，
WARNING 为重试/补偿失败等异常状态，ERROR 为失败，
CRITICAL 为无法工作；不要将所有业务拒绝都记为 ERROR。

验证事件字段、request/correlation/task 上下文、敏感字段与 URL 脱敏、
未知异常记录、上下文清理，不对带颜色控制台整行做脆弱快照。

普通日志不替代合规审计。ELK/Loki、Sentry、Prometheus、OpenTelemetry、
审计存储与慢任务监控不作为 v0.1 默认依赖或平台功能。
