# 响应与异常

M2 已实现响应类型、公共错误描述符、应用异常分类与集中 HTTP 处理器。
业务模块的专用错误随对应里程碑加入。

## 统一响应

JSON 业务成功响应：

```json
{"code": 0, "message": "success", "data": {}}
```

无业务返回值时 data 为 null；分页放入 data，结构见 [api](api.md)。
ApiResponse[T] 保留具体响应类型，不把所有结果降为无类型字典。

错误使用 numeric code、安全 message、data（通常为 null），可以附带 request_id。
成功响应体不默认添加 request_id；HTTP 响应通过 X-Request-ID 返回关联标识，
包括未知异常的 500 响应。

验证错误的 data 使用 errors 列表，每项包含 field、message、type；
字段路径去掉框架来源前缀，不返回原始输入、异常对象或敏感上下文。
v0.1 不实现完整错误国际化。

响应类型位于 `app/common/response.py`，`Page` 位于 `app/common/pagination.py`。
成功响应显式构造 `ApiResponse[T](data=...)`，
无返回值用 `ApiResponse[None](data=None)`；分页使用 `ApiResponse[Page[T]]`。
错误体总是包含 request_id。验证错误的 message 固定为 `Field required` 或
`Invalid value`，不回显可能包含输入值的 Pydantic/自定义校验器 msg 和 ctx。

## HTTP 状态

| 场景 | HTTP |
| --- | --- |
| 查询、更新、删除、登录成功 | 200 |
| 资源创建成功 | 201 |
| 异步工作已接受 | 202 |
| 请求语义不合法 | 400 |
| 未认证、无效凭据或 Token | 401 |
| 已认证但无权限 | 403 |
| 资源或路由不存在 | 404 |
| 方法不允许 | 405 |
| 唯一资源或业务状态冲突 | 409 |
| 上传过大 | 413 |
| 文件类型不允许 | 415 |
| Schema 验证失败 | 422 |
| 请求受限（扩展语义，非内置限流功能） | 429 |
| 未知内部异常 | 500 |
| 请求所需基础设施不可用 | 503 |

默认业务 DELETE 返回 200 加 envelope；204 不得携带 JSON body。
错误不能统一伪装为 HTTP 200。下载、流式响应、重定向等不强制使用 envelope。

## 错误描述符

稳定 ErrorDescriptor 包含 `code`、`key`、默认安全 `message`、`status_code`。
公共错误位于 Core，业务错误位于模块 errors.py，避免全局巨大枚举。
`core/exceptions/descriptors.py` 定义 ErrorDescriptor，`common.py` 定义公共错误，
`base.py` 定义异常类；`handlers.py` 负责 HTTP 转换，由 `bootstrap/exceptions.py` 注册。
`core/exceptions/__init__.py` 保留异常与描述符公共导入入口，不加载 HTTP Handler。
数字码和 key 唯一，不能在抛出点临时拼凑数字或泄漏底层错误文本。

保留既有类别：系统 10000 段、基础设施 11000 段、认证 20000 段、
授权 21000 段、User 30000 段、File 31000 段、验证 40000 段。
不为未来模块预分配大量范围。

既有关键规划映射：

| key | code | HTTP |
| --- | --- | --- |
| INTERNAL_ERROR | 10001 | 500 |
| HTTP_ERROR | 10002 | 其他 HTTP 错误保留原状态，默认 400 |
| NOT_FOUND | 10003 | 404 |
| METHOD_NOT_ALLOWED | 10004 | 405 |
| INFRASTRUCTURE_UNAVAILABLE | 11001 | 503 |
| INVALID_CREDENTIALS | 20001 | 401 |
| PERMISSION_DENIED | 21001 | 403 |
| USER_ALREADY_EXISTS | 30001 | 409 |
| USER_NOT_FOUND | 30002 | 404 |
| USER_DISABLED | 30003 | 403 |
| USER_SELF_DELETE | 30004 | 403 |
| FILE_NOT_FOUND | 31001 | 404 |
| FILE_TOO_LARGE | 31002 | 413 |
| FILE_TYPE_NOT_ALLOWED | 31003 | 415 |
| FILE_INVALID_NAME | 31004 | 422 |
| VALIDATION_ERROR | 40001 | 422 |

当前已实现公共描述符及表中全部 User/File 描述符。
应用 401 响应统一包含 WWW-Authenticate: Bearer，不泄漏令牌解析细节。
描述符为不可变数据类；`BusinessException` 显式接收模块描述符，认证、授权和
基础设施异常分别默认使用 INVALID_CREDENTIALS、PERMISSION_DENIED 和
INFRASTRUCTURE_UNAVAILABLE。HTTP 状态由描述符确定，不由异常类另行推断。

## 异常转换边界

Service 抛应用异常，禁止 HTTPException/JSONResponse。
AppException 及业务、认证、授权、基础设施分类保持小而明确，HTTP 状态由描述符确定。

Bootstrap 集中注册应用异常、请求验证异常、Starlette HTTPException 和未知异常处理器。
应用 JSON API 的 422、路由 404、405、500 都不能漏出默认 detail。
Router 不重复捕获正常业务异常。

原生 HTTPException 的 detail 一律不回显；已知状态使用公共描述符，其余使用
HTTP 标准短语和 HTTP_ERROR 编号，保留 Allow、WWW-Authenticate、Retry-After 等头。
SafeExceptionMiddleware 在框架 DEBUG 错误页之前调用未知异常处理器，所以开发模式也返回安全 JSON；
该层位于 CORS 内侧，错误响应保留跨域头，外侧请求上下文统一附加请求 ID。
流式响应已开始时无法更改状态或响应体；此时仅记录一次诊断并继续传播异常以中止连接，
不发送第二组响应头。

Adapter 将厂商错误转换成稳定基础设施错误，Service 决定业务语义。
数据库唯一约束冲突只在明确识别后转业务错误，不把所有 IntegrityError 归为重复用户。
CLI 将同一应用异常映射成人类可读错误和非零退出码。

未知异常对外只返回安全 500，详细诊断经过脱敏后内部记录一次。
连接池超时、SQLAlchemy 明确标记的连接失效，以及 SQLite BUSY（包括扩展错误码）
由中央处理器返回 503 / INFRASTRUCTURE_UNAVAILABLE；不按异常文本猜测，也不将任意 SQL 错误降为 503。
默认不重放事务：跨数据库/对象存储操作可能已经部分生效，调用者须结合幂等性与资源状态决定重试。
响应不得包含 traceback、SQL、数据库约束内部细节、文件系统路径、
SDK 错误对象、密码或 Token。测试必须覆盖错误唯一性、HTTP 映射、脱敏与 OpenAPI 一致性。
