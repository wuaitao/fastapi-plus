# 新旧脚手架对照与上线收口

日期：2026-09-13。基线为完成 M0–M9 和全量审计的 `0.1.0.dev0`。
对照对象是本地 `fastapi-scaff/fastapi-scaff-main`；该目录仅供参考，不随新模板交付。
本轮围绕真实接入与维护细节收口，不扩大 auth/user/file 的业务范围。

## 对照与取舍

表中旧路径相对于参考项目根目录；新路径相对于当前项目。旧项目作为设计参考，
本次实现沿用新项目的类型化配置、原生中间件和显式 Bootstrap，未复制旧项目实现代码。

| 细节 | 旧项目证据 | 当前项目与决定 |
| --- | --- | --- |
| 应用名称与文档说明 | `app/core/_conf.py` 的 APP_TITLE/SUMMARY/DESCRIPTION，`app/main.py` 注入 FastAPI | 采纳，新增同名配置，直接传入原生 FastAPI；默认名称保持 FastAPI Plus |
| 版本展示 | APP_VERSION 同时用于文档和 health | 采纳统一来源的意图；OpenAPI 改读已安装的 fastapi-plus 元数据，与 CLI 一致，不再硬编码第二份版本；health 保持存活契约 |
| 浏览器跨域 | `app/core/middleware.py` 原生 CORS 子类，`_conf.py` 提供来源/方法/头 | 采纳显式接入能力；默认关闭，来源白名单，固定现有 Bearer API 所需方法/头；不沿用通配来源加凭据的默认值 |
| 请求关联与响应头 | HttpMiddleware、`app/core/context.py`、Responses 的 request_id | 已有更严格的格式/重复头校验、上下文隔离与错误关联；补上浏览器读取 X-Request-ID 和 Content-Disposition |
| 安全错误和流式输出 | Responses 区分 JSON 与 stream，HttpMiddleware 统一兜底 | 保留原生流式响应与安全 JSON；兜底移到 CORS 内层，预检留在上下文内，测试验证已开始的流不发送第二组头 |
| 配置分组与来源优先级 | `_conf.py`、环境 YAML、环境变量覆盖 | 当前冻结 Settings、能力分组、SecretStr 与来源测试已覆盖；不增加第二套 YAML 加载器或配置前缀 |
| 数据库连接与事务 | `_db.py` 的 pre_ping、recycle、SQLite 参数区别，Service 显式 commit | 当前 engine 已有 pre_ping/recycle，独立 Session 与三数据库迁移验收；保留现有实现，不复制自动建表或同步/异步双引擎 |
| 模型、分页与序列化 | User 的索引/唯一字段、list_user 的分页与字段筛选、ID 字符串化 | 当前数据库约束、分页上限、Schema 序列化已有覆盖；手机号/昵称筛选与个人资料字段属于旧业务，不新增到参考模块 |
| JWT 与退出 | `app/api/deps.py`、`app/services/user.py` 的每用户签名密钥和 Cookie refresh | 不迁移认证协议；保留 Argon2id、固定签名算法、状态检查、Bearer 与 TokenStore。旧项目固定 JWT_KEY 时不能靠同值更新撤销，不能直接作为可靠退出方案移植 |
| Redis | `_redis.py` 提供客户端与连接参数 | 当前显式开关、5 秒超时、启动 PING 和关闭释放已满足范围；不为了对齐而新增参数平台 |
| Celery | 独立生产者/消费者、任务注册表、JSON、重试/超时/队列配置 | 当前独立 Worker、显式注册、JSON、有限暂时故障重试与关联上下文已有覆盖；不照搬任意 Exception 重试、自动扫描或固定并发数 |
| CLI 与迁移 | `runserver.py`、`runmigration.py`、Alembic env | 保留原生 Uvicorn CLI 与当前 fastplus 命令；不新增启动器或运行时安装依赖。迁移保持显式模型注册与 NullPool |
| 日志与健康检查 | 启停信息、文件日志、`/health`、提交任务的 `/ahealth` | 当前 structlog stderr 适合进程管理收集；doctor 提供只读诊断。无业务依赖的存活探针保持轻量，不引入有发送副作用的探针 |
| 模板与部署便利 | scaff new/add/tpl、Docker、Gunicorn 入口 | 超出 v0.1 Template-first 范围，保留原生工具与部署文档，不引入生成器或部署平台 |

数据库模型、迁移和业务路由未变。没有新增运行时或开发依赖，`pyproject.toml`、`uv.lock` 保持不变。

## 本次落地

1. `core/config/app.py` 增加应用文档元数据及不可变 CORS 来源白名单。
   来源要求协议/主机/可选端口，拒绝通配符、凭据、路径、尾斜线、查询、片段和非法端口。
2. `bootstrap/application.py` 使用已安装的项目版本；`bootstrap/middleware.py` 显式组合原生 CORS。
   请求顺序为上下文 → CORS → 安全异常兜底 → 路由。
3. 原 `core/logging/context.py` 的异常转换移至 `core/exceptions/middleware.py`，保持纯 ASGI。
   预检也有请求 ID/完成日志，普通未知异常转换出的 500 在 DEBUG 开关两种状态下均可安全跨域读取。
4. `.gitattributes` 固定 Python 为 LF。实测既有三个文件使用 CRLF，与 Ruff 的 LF 配置冲突；
   只统一换行符，不修改这些文件的逻辑，也不放宽质量检查。
5. `.env.example`、README、配置/API/安全/日志/错误/测试文档和代码树同步。

配置示例和限制见 [configuration](configuration.md#业务名称与浏览器跨域)。
原生预检返回纯文本 200/400；CORS 不替代认证，跨域 Cookie 仍未启用。
云下载重定向之后的响应由目标桶控制，需要单独配置其 CORS。

## 验证记录

本轮在 Windows / Python 3.13.15、现有锁文件上运行。新增场景先验证缺口，再实现与回归。
首次基线的 CLI/独立导入失败来自 `.venv` 中无法覆盖的旧可编辑安装记录；
按锁文件重新安装当前项目修复权限阻碍后的安装状态，没有通过 PYTHONPATH 或修改测试绕开。

| 检查 | 本轮结果 |
| --- | --- |
| uv sync --locked | 通过；重新安装当前项目后，CLI/独立导入边界回归通过 |
| Ruff lint / format | 通过；139 个 Python 文件符合格式要求 |
| Pyright strict | 0 errors、0 warnings |
| coverage run -m pytest | 409 passed，无 skip/xfail；较基线增加 29 项 |
| 语句与分支综合覆盖率 | 整体 95.31%；Core 98.04%；Security 100.00%；Database 93.46%，均达到门槛 |
| OpenAPI 与架构边界 | 全量测试覆盖；现有业务路径、响应和 Bearer 契约保持，文档元数据配置生效 |
| SQLite 迁移与核心集成 | 全量测试包含真实升级/check/降级/再升级与 Auth/User/File 发布流程 |
| CORS | 默认关闭、预检与拒绝、成功/错误、DEBUG、流式分块/中止及上下文测试通过 |
| Git 换行符 / 差异 | Python eol=lf 属性核对与 diff --check 通过；三处既有 CRLF 仅统一换行符 |
| 文档与配置示例 | 23 份 Markdown、117 个本地链接/锚点核对通过；隔离外部环境变量后加载 .env.example 并创建应用通过 |

复现命令见 [testing](testing.md#发布质量)。覆盖率未排除新文件，也未调整门槛。

## 发布边界

本轮完成代码与文档收口，不代表已经部署生产或发布 0.1.0。
三数据库和真实 Redis/Worker 的历史通过记录保留在 [release](release.md) 与 [audit](audit.md)，
本轮不把历史执行记为重新运行。目标环境、真实云存储、版权主体与正式版本/标签等发布待办仍按
[发布验收](release.md#已知限制与正式发布待办)处理；未提供生产配置或云账号时不宣称已完成实际上线验收。

实现前通过 Context7 核实 [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)、
[中间件顺序](https://fastapi.tiangolo.com/tutorial/middleware/#multiple-middleware-execution-order)
及 [应用元数据](https://fastapi.tiangolo.com/tutorial/metadata/)。
