# 文件与存储

M6 已实现 Provider/Registry、Local、OSS/COS Adapter、File 模块及 `0002_create_files` 迁移。
契约位于 `app/providers/storage.py`，装配位于 `app/bootstrap/providers.py`。
Adapter 位于 `app/infrastructure/storage/{local,aliyun_oss,tencent_cos}.py`，
共享键名检查及云错误转换保留在同目录 `common.py`；后端标识仍为 local/oss/cos。

## 当前使用方式

先执行 `uv sync` 和 `uv run alembic upgrade head`。默认后端为 Local，
不需要云 SDK 或云凭据；文件存入 `data/storage/{private,public}`，两目录均不静态挂载。
业务路径统一为 `/api/v1/files`，上传为 multipart，字段为 `file` 和可选的 `visibility`。
上传返回 201；元数据、下载和删除成功返回 200，云下载返回 307；删除 envelope 的 data 为 null。

登录用户可上传，默认 `private`。私有元数据与下载仅允许所有者或超级管理员，
匿名返回 401、其他用户返回 403；公开文件可匿名读取。任何文件删除都要求所有者或超级管理员。
删除用户后保留文件，created_by 置 null，私有文件仅超级管理员可管理。
公开元数据的 url 指向下载路由；私有 url 恒为 null。签名 URL 不写入数据库。

`FILE_MAX_SIZE` 默认 10485760 字节（10 MiB），Service 分块检查实际流大小。
文件名最多 255 字符，不接受路径分隔符、盘符、控制字符和首尾空白。
当前允许列表在 `modules/file/service.py` 的 `ALLOWED_TYPES` 中显式定义：

| 扩展名 | 必须匹配的 Content-Type |
| --- | --- |
| .txt | text/plain |
| .pdf | application/pdf |
| .png | image/png |
| .jpg / .jpeg | image/jpeg |
| .bin | application/octet-stream |

不使用原始文件名作为路径，服务器生成 UUID key。下载均使用 attachment 和原始文件名。
上传由框架暂存后交给 Service 分块检查；该大小限制不是反向代理层的请求体限制。
校验与 Adapter 的阻塞读写在线程中执行；请求取消时先等待正在读取上传流的线程退出，
再向入口传播取消，避免 Router 的 finally 提前关闭文件。取消校验不会继续写入对象或元数据。

## 云后端配置

OSS 使用官方 `alibabacloud-oss-v2`（Apache-2.0），COS 使用 `cos-python-sdk-v5`（MIT）。
SDK 的依赖留在 extras；COS 的 CRC 依赖可能在当前平台编译，Local 不受影响。
新增核心依赖仅 `python-multipart`（Apache-2.0），用于 FastAPI 原生 multipart 解析。
参考 [OSS SDK](https://pypi.org/project/alibabacloud-oss-v2/)、
[COS SDK](https://pypi.org/project/cos-python-sdk-v5/) 与
[multipart](https://pypi.org/project/python-multipart/)。

按需执行 `uv sync --extra oss`、`uv sync --extra cos`，或同时指定两个 extra。
设置 `STORAGE_BACKEND=oss` 或 `cos`，并通过环境变量提供对应配置：

```dotenv
# 以下为变量名说明，秘密由部署环境注入，不填写或提交真实值。
STORAGE_OSS__BUCKET=your-test-bucket
STORAGE_OSS__REGION=cn-hangzhou
# STORAGE_OSS__ACCESS_KEY_ID=
# STORAGE_OSS__ACCESS_KEY_SECRET=
STORAGE_COS__BUCKET=your-test-bucket-appid
STORAGE_COS__REGION=ap-guangzhou
# STORAGE_COS__ACCESS_KEY_ID=
# STORAGE_COS__ACCESS_KEY_SECRET=
```

仅设置实际启用后端的完整字段；COS 的 ACCESS_KEY_ID/SECRET 分别对应 SecretId/SecretKey。
提供配置即显式注册该后端，切换默认后端后须保留历史后端配置与 SDK，Local 始终注册。
端点按 region 生成，使用 HTTPS；对象按 public/private 前缀隔离并显式设置对象 ACL。
使用专用桶，桶策略不能额外授予 private 前缀公共读取权限；公开对象需允许 public-read ACL。
私有访问先鉴权再签名，地址有效期为 300 秒；公开下载也通过 300 秒签名保留 Unicode 下载名。

普通契约测试只模拟 SDK 边界。真实云验证入口为 `tests/manual_storage_cloud.py`，
不被默认 Pytest 收集；使用专门测试桶和最小权限凭据，设置
`LIVE_STORAGE_OSS_BUCKET/REGION/ACCESS_KEY_ID/ACCESS_KEY_SECRET` 或同名 COS 变量后显式执行：

```bash
uv run --extra oss pytest tests/manual_storage_cloud.py -k oss
uv run --extra cos pytest tests/manual_storage_cloud.py -k cos
```

该检查会创建 UUID 测试对象、验证上传/下载/真实 ACL/幂等删除，并在 finally 清理。
没有专用云凭据时不要运行；本次交付不声称已完成真实云联调。

## 架构与契约

```text
FileService → StorageRegistry → StorageProvider → Local / Aliyun OSS / Tencent COS
     ↓
FileRepository → Database
```

Local 为默认后端；Aliyun OSS、Tencent COS 是 v0.1 必须完成的可选 Adapter。
File 是业务资源；Storage 只管理内容与访问能力，不做用户权限或文件处理业务。

Provider 最小能力为 put、exists、delete 与 URL/访问策略。
内容使用流或 file-like 对象，结果为统一 StoredObject；
不得将 UploadFile、HTTP 响应或 SDK 对象变成跨层契约。
服务返回应用结果，Router 构造实际下载/重定向响应。

StorageRegistry 保持轻量，按显式注册的 backend 选择 Provider。
上传选择默认后端，历史文件访问使用记录中的 backend，不能因切换默认值而读错文件。

## 元数据与访问

FileRecord 保存 ID、backend、key、original_name、content_type、size、visibility、
created_by、时间及按需 checksum。API URL 动态生成，backend + key 才是定位事实源。

默认私有。私有元数据响应不自动生成永久公网地址，url 默认 null。
Local 私有文件通过授权下载接口访问，不允许无鉴权 StaticFiles 挂载。
公开本地文件可单独暴露 public 目录，不能连带暴露 private。

云私有文件先授权，再生成短期签名访问地址或重定向；
既有建议有效期为 300 秒。安全策略不依赖厂商。
下载使用原始文件名作展示元数据，正确处理 Unicode Content-Disposition。

## 上传安全

服务器生成规范化 object key，原始文件名只作元数据。
验证文件名、扩展名、Content-Type 和实际流大小；不能只相信客户端长度。
扩展名与客户端 MIME 均不构成完整内容安全证明，扫描能力留作后续扩展。

Local 目标路径解析后必须仍在配置根目录内，
考虑绝对路径、父目录跳转和符号链接逃逸。
运行内容存放 data/storage，与源码分开，不进入版本控制。

分块/流式处理，不无界 read 整个大文件入内存；
云 SDK 阻塞调用由 Adapter 隔离到线程等适当边界，不阻塞事件循环。
上传过大映射 413，类型不允许映射 415，存储不可用映射 503。

## 数据库与对象存储一致性

v0.1 采用明确的简化上传流程：

1. 校验并生成 key。
2. 写入对象存储。
3. 创建元数据并由 Service 提交数据库事务。
4. 数据库写入或提交失败时回滚，并尽力删除刚写入的对象。

数据库与对象存储不是原子事务。补偿失败记录安全日志，不覆盖原始错误，
不能声称已恢复完整一致性；代码须有中文说明与失败路径测试。
不提前构建 PENDING/PROCESSING 等复杂状态机。

删除先授权并读取记录，再删除对象和元数据，由 Service 完成事务。
Provider 删除已不存在对象应幂等；不能把存储故障当作成功。
跨系统删除失败仍可能产生不一致，应明确报告，而非用数据库回滚假装恢复对象。

## 验收与非目标

Local 使用真实临时文件系统验证上传、下载、删除、同名与 Unicode 文件、
路径安全、private/public 分离和较大流。
Local/OSS/COS 使用同一行为契约；普通测试可模拟云 SDK 边界，
保留使用专门测试凭据的可选真实云集成验证。

验证本地模式无需任何云依赖，以及数据库失败补偿和补偿失败。
v0.1 不实现分片续传、浏览器直传、全局去重、回收站、病毒扫描、
图片处理平台、存储迁移工具或自制 Range Server。
