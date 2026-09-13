# 参考模块

v0.1 仅包含 auth、user、file，作为可运行的架构示例。
M4 已实现 user 模块，M5 已实现 auth；M6 已实现 file。
模块、迁移、测试和文档需一起演进；未来若增加生成器，其模板也应保持一致。

## User（M4，M5 补齐认证授权）

字段保持最小：id、username、可空 email、password_hash、
is_active、is_superuser、created_at、updated_at。
username 唯一，非空 email 唯一，使用具名数据库约束。

M4 已提供完整 CRUD、分页与 `0001_create_users` 迁移。用户名为 1–64 个
ASCII 字母、数字、下划线、点或连字符；email 校验格式且最多 254 字符。
创建密码为 8–128 字符，使用 argon2-cffi 的 Argon2id 和随机盐，在线程中计算。
创建仅接受 username、email、password、is_active；is_superuser 固定为 false。
查询仅接受 page/size，固定按 ID 升序；空 PATCH 保持原值，email=null 清空邮箱。
创建直接通过具名唯一约束判断冲突，避免 SQLite 先查询再插入造成的锁升级竞争；
更新预检查排除用户自身，写入时仍由数据库约束兜底。

UserCreate、UserUpdate、UserQuery、UserResponse 分开：
普通 PATCH 不接受 password 或 is_superuser 等敏感变更，
响应绝不包含密码及哈希。资源 ID 在响应中使用字符串。

UserRepository 查询并返回 ORM；UserService 完成业务校验、
PasswordHasher 调用、唯一冲突转换与事务；Router 序列化输出。
不存在返回明确业务错误，不将任意数据库错误误报为重复用户名。

最终管理权限以 is_superuser 和简单 permission hook 示范，
不增加角色关系表。Service 示范“管理员不能删除自己”的业务规则。
M5 已接入 Bearer 认证、超级管理员权限与自删规则；M8 CLI 已提供显式管理员创建。
UserService.delete_user 要求显式 actor_id，HTTP/CLI/Worker 均受自删规则约束。

验收包括 CRUD、分页、用户名/email 重复、并发冲突兜底、
404、密码不泄漏、PATCH 敏感字段限制与自删规则。
M5 不创建默认账号，不增加用户自助注册或管理员引导端点。

## Auth（M5）

复用 UserRepository、PasswordHasher、TokenProvider 和可选 TokenStore；
不为目录对称增加 auth 表或没有用途的 Repository。
业务方法为 login、refresh、logout、get_current_user。

Service 返回 TokenPair 等应用结果，Router 输出 TokenResponse；
Token 响应包括 access_token、refresh_token、token_type、expires_in。
当前用户通过 auth/me 获取，不将完整用户或菜单塞入 Token 响应。

刷新检查签名、有效期、type 和用户状态；
默认 stateless 退出的限制及错误语义见 [security](security.md)。
验收覆盖错误凭据、禁用用户、过期/类型混用、刷新与当前用户。

## File（M6）

FileService 协调 FileRepository 与 StorageRegistry。
FileRecord 保存 backend + key 和最小元数据，URL 不作为事实源；
private 为默认，公开元数据不自动发放私有签名 URL。

上传校验、对象写入、数据库事务与失败补偿遵循 [storage](storage.md)。
下载先做业务授权，再由 Router 返回文件或重定向；
Provider 不依赖用户、Role 或 HTTP。

验收包括上传、大小/类型拒绝、私有下载、删除、历史 backend 选择、
数据库失败补偿、Local 真实文件系统和 OSS/COS 契约。
M7 的唯一 Task/Handler 示例位于 user 模块，默认上传不触发 Celery。

## 共同约束

接口清单集中在 [api](api.md)，不维护多套 endpoint 定义。
默认表只有 users、files、alembic_version；
users/files 迁移分别在 M4/M6 引入，避免提前创建未来表。

不扩展第四个默认业务模块，不加菜单、部门、字典、通知、租户或工作流。
默认完整体验仅需 Python、SQLite、Local 文件系统；
云后端、Redis 和 Celery 不得变成基础导入或运行的强依赖。
