# 安全

本文描述 v0.1 安全要求；M5 已实现密码哈希、JWT、认证与最小授权。

## 认证基础与业务

密码使用 argon2-cffi 提供的 Argon2id；JWT 使用 PyJWT。
库在功能里程碑加入，不实现自制密码哈希或 Token 签名算法。

Core Security 提供异步 hash_password/verify_password，复用注入的 PasswordHasher，
在线程中调用原生库；不存在的账号也验证随机虚拟哈希，减少耗时差异。
Core Security 负责 Token 编解码；TokenStore 契约位于 `app/providers/token_store.py`，
同文件保留无外部依赖的默认 NullTokenStore，由 Bootstrap 装配；
auth 模块负责登录、刷新、退出、当前用户和用户状态检查。
认证依赖调用应用服务，不在 Router 中解析 Token 或查询用户。
当前用户依赖在独立短 Session 中完成查询并释放读事务，返回仅供身份判断的已加载快照；
公开文件的可选身份解析复用相同流程，无效 Bearer 仍按认证失败处理。

密码只保存哈希，不输出原始密码或哈希。既有基础长度策略为 8–128，
不强制复杂字符组合；安全策略可由具体业务收紧。
不创建默认管理员或默认密码，管理员在 M8 通过显式 CLI 交互创建。

## Token 与状态

使用 HTTP Bearer，JWT access/refresh token 类型明确区分。
默认 access 30 分钟、refresh 7 天，必要声明为 sub、type、iat、exp、jti；
sub 使用字符串。Token 不携带菜单、完整用户资料或大量权限数据。

默认签名方案为 HS256，秘密来自配置；不硬编码生产秘密。
生产必须配置至少 32 字节的随机 JWT_SECRET，缺失或过短时配置校验失败。
开发/测试未配置时，由应用工厂生成实例级随机密钥；重启后旧令牌失效，
多进程部署应显式配置共同秘密。秘密配置及有效期字段见 [configuration](configuration.md)。
校验固定允许算法、签名、有效期、Token 类型和用户存在/启用状态。
声明类型严格检查，非有限时间值等转换错误统一作为无效 Token 拒绝，不泄漏解析异常。
刷新同样重新验证用户状态，不能只解码后重新签发。

用户不存在、密码错误和被禁用时的登录失败统一为 401 invalid credentials，
避免账号枚举。持有效 Token 的已禁用用户按 USER_DISABLED 返回 403。
未认证用 401，已认证但无权限用 403。

## Stateless 模式与 TokenStore

默认不依赖 Redis，以 stateless JWT/NullTokenStore 运行。
该模式的退出只表示客户端删除 Token；已签发 Token 在过期前仍可能有效，
不能宣称已完成服务端撤销或防重放。
logout 验证 Bearer access token 后调用 TokenStore；NullTokenStore 的撤销为空操作。
refresh 签发新的一对令牌，但不消费旧 refresh token；客户端应删除本地旧令牌。

TokenStore 是可替换能力；当前未提供 RedisTokenStore，启用 Redis 也不会自动启用撤销。
Token 撤销存储使用 jti 与到期时间，不保存或记录完整 Token。
刷新轮换、会话管理等扩展须说明状态存储依赖，不作为默认隐含能力。

## 授权与请求安全

v0.1 仅要求认证、is_superuser 和最小 permission hook。
权限名可用 resource:action；管理接口由依赖声明权限。
当前全部 users 接口分别声明 user:create/read/update/delete，仅 is_superuser 可通过。
`core/security/dependencies.py` 负责通用 Bearer 解析，不导入用户模型。
`auth/dependencies.py` 的 require_permission 将 CurrentUserDep 查询到的用户状态
交给 `core/security/permissions.py` 的 check_permission；通用策略不依赖业务模块。
Service 保留资源所有权、不可自删等业务规则，供 CLI/Worker 复用。

不内置 Role/Permission 关系表、菜单、部门数据范围、租户、工作流、
SSO/OAuth/OIDC、验证码平台或复杂授权引擎。

跨域通过 `CORS_ALLOW_ORIGINS` 明确白名单启用 FastAPI 原生 CORS，默认关闭，
拒绝通配来源且不启用跨域 Cookie 凭据；配置和边界见 [configuration](configuration.md#业务名称与浏览器跨域)。
CORS 不替代认证或阻止非浏览器访问。未提供通用安全响应头平台，HSTS 等策略由 HTTPS 部署配置。
文件下载已设置 attachment、no-store 和 nosniff，Token 响应设置 no-store。
当前认证通过 Authorization 传输；若未来改成自动携带的 Cookie，
必须重新评估 CSRF 防护，不能将 JWT 等同于无 CSRF 风险。

上传及私有文件访问见 [storage](storage.md)。
敏感数据与错误脱敏见 [logging](logging.md) 和 [errors](errors.md)。
限流、登录防护、审计等仅为后续扩展方向，不预装实现或额外服务。

## 验收

覆盖密码验证、错误凭据、无效签名、过期、两种 Token 混用、
禁用用户、刷新状态检查、401/403、无默认账号与敏感信息泄漏。
生产秘密缺失必须在启用相应功能时启动失败。
