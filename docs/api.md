# API 契约

本文是 v0.1 API 契约；M1 已实现 Health，M2 已实现响应、分页与全局错误格式。
M4 已实现 User 路由；M5 已实现 Auth 和用户管理授权，M6 已实现 File。

## 路径与方法

业务 API 默认前缀 `/api/v1`，在 Bootstrap 统一组合。
模块声明复数资源路径，使用 GET、POST、PATCH、DELETE。
更新采用 PATCH；不建立 getUser/createOrder 风格 RPC URL 或上传兼容别名。

| 模块 | 当前路径与方法 |
| --- | --- |
| Health（M1） | GET /health |
| Auth（M5） | POST /api/v1/auth/login、refresh、logout；GET /api/v1/auth/me |
| User（M4–M5） | POST、GET /api/v1/users；GET、PATCH、DELETE /api/v1/users/{id} |
| File（M6） | POST /api/v1/files；GET、DELETE /api/v1/files/{id}；GET /api/v1/files/{id}/download |

Auth 表中的 refresh/logout 与 login 共用 `/api/v1/auth/` 前缀。
Health 是简单进程存活探针，返回 `{"status": "ok"}`，不执行数据库检查。
不增加菜单、权限查询、批量 CRUD 或用户自助注册端点。

M4 用户创建成功返回 201，查询、PATCH 和 DELETE 返回 200；DELETE 的 data 为 null。
用户名或非空 email 冲突返回 409 / USER_ALREADY_EXISTS，用户不存在返回
404 / USER_NOT_FOUND，输入校验失败返回统一 422。M5 起所有 users 接口要求
Bearer access token 与超级管理员权限；未认证 401、无权限 403，自删 403 / USER_SELF_DELETE。
创建与更新字段、长度和密码策略见 [User 参考模块](reference-modules.md)。

### Auth 输入与响应（M5）

- login 接受 JSON `{"username":"已有用户名","password":"用户密码"}`。
- refresh 接受 JSON `{"refresh_token":"已签发的 refresh token"}`。
- logout 无需请求体，使用 `Authorization: Bearer <access_token>`。
- me 使用同一 Bearer 头，返回 `ApiResponse[UserResponse]`，不包含密码或哈希。

login/refresh 返回 200 和统一 envelope，data 包含 access_token、refresh_token、
token_type（bearer）、expires_in（access 有效秒数）；响应带 Cache-Control: no-store。
logout 返回 200 和 data=null。默认退出只要求客户端删除两个令牌，服务端不撤销；
旧 refresh token 在到期前也可再次使用，无状态模式不提供轮换防重放。
登录账号不存在、密码错误或禁用均为 401 / INVALID_CREDENTIALS。
无效、过期、错误类型令牌或用户已删除为 401；有效令牌对应的禁用用户为
403 / USER_DISABLED。401 响应携带 WWW-Authenticate: Bearer。

## 输入与序列化

File 创建接受 multipart `file` 和可选 `visibility=private|public`，成功返回 201。
文件输出包含字符串 id/created_by、backend、key、original_name、content_type、size、
visibility、created_at、updated_at、url；private 的 url 恒为 null，public 指向下载接口。
上传要求登录；私有读取及所有文件删除要求所有者或超级管理员，public 读取可匿名。
本地下载返回原始文件内容，云下载返回 307 和 300 秒签名地址，均不封装 JSON。
下载使用 Unicode attachment 文件名和 Cache-Control: no-store。
文件缺失 404、过大 413、类型不允许 415、文件名无效 422、存储不可用 503；
完整允许类型与配置见 [storage](storage.md)。

JSON 输入使用 Pydantic Schema；文件创建使用 multipart 输入。
创建、PATCH、查询、输出模型各有明确意图；输出不包含密码或 password_hash。
业务对象不存在时返回 404，不能以成功加 null 表达。

数据库 ID 保持整数；存在 JavaScript 精度需求时在响应 Schema 中序列化为字符串。
参考模块的资源 ID 采用字符串输出，在 OpenAPI 和测试中保持一致；
不用 Router 到处手工转换。日期时间采用 UTC 的 ISO 8601 表达。

## 列表

分页默认 `page=1`、`size=20`，要求 page >= 1、1 <= size <= 100。
返回的 data 包含 `items`、`total`、`page`、`size`；空列表为 []。
不增加可推导的 pages/has_next 字段，不同时构建游标分页体系。

每个模块显式选择过滤字段。需要排序时使用 `sort_by`、`sort_order`，
只允许已声明字段；不提供通用多字段排序 DSL 或任意数据库字段查询。

## 响应与 OpenAPI

JSON 业务响应使用 code/message/data，状态码与错误规则统一见 [errors](errors.md)。
下载、重定向、流式响应不包裹 JSON；框架文档与 Health 保持各自格式。

Router 声明 summary、描述、tags、最终响应 Schema 与适用错误响应。
OpenAPI 必须反映实际泛型响应、字符串 ID、HTTP Bearer 认证和自定义 422。
不能运行时返回统一错误，文档却仍宣称 FastAPI 默认 detail 格式。

应用工厂声明公共 404/405/422/500/503 的 ErrorResponse 和 X-Request-ID 响应头，
覆盖 FastAPI 默认 422 Schema。模块使用原生 `responses` 声明其余适用错误，
使用 `ApiResponse[T]` 或 `ApiResponse[Page[T]]` 作为最终响应类型；不自动包裹响应体。

数据库明确的暂时不可用（连接池耗尽、已失效连接、SQLite BUSY）返回 503 / 11001，
区别于唯一冲突 409 与未知故障 500。并发边界、回滚与重试要求见 [数据库](database.md#查询与事务)。

前端仅依赖公开 API 契约，不绑定任何 Admin UI。
公开契约变更需同步文档和 API/OpenAPI 测试。
