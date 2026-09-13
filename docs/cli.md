# 项目 CLI

M8 使用 Typer 提供当前项目命令。先执行 `uv sync` 安装 `fastplus` 入口，
在项目根目录通过 `uv run fastplus ...` 调用，或激活虚拟环境后直接调用。

## v0.1 命令范围

| 命令 | 行为 |
| --- | --- |
| fastplus version | 展示项目和相关运行时版本 |
| fastplus doctor | 只读检查配置、连接、迁移状态和存储条件 |
| fastplus db revision | 薄封装 Alembic revision |
| fastplus db upgrade | 显式升级到指定 revision，默认 head |
| fastplus db downgrade | 显式回退指定 revision |
| fastplus db current | 查看当前迁移版本 |
| fastplus create-superuser | 交互创建管理员，不预置密码 |

CLI 不是包管理器、迁移引擎或生产部署平台。本次 M8 不包含 `fastplus run`；
开发运行继续使用 `uv run uvicorn app.main:app --reload`。

```bash
uv run fastplus version
uv run fastplus db revision -m "add field" --autogenerate
uv run fastplus db upgrade
uv run fastplus db current
uv run fastplus db downgrade -- -1
uv run fastplus create-superuser
uv run fastplus doctor
```

`db` 使用当前目录的 `alembic.ini`，复用已有 Alembic 环境和配置加载。
`revision` 必须提供 `-m/--message`；不加 `--autogenerate` 时只生成空迁移，不连接数据库。
`upgrade [REVISION]` 默认 `head`；`downgrade REVISION` 必须明确目标，
负数 revision 前使用 `--`，例如 `downgrade -- -1`；`downgrade base` 回退全部迁移。
迁移文件需人工审查，命令不隐式创建数据库的父目录。

`create-superuser` 依次询问 Username、可留空的 Email 和两次 Password。
用户名为 1–64 位字母、数字、下划线、点或连字符；密码为 8–128 字符。
复用 UserCreate 校验及 UserService，单次事务创建已激活的超级用户，
重复用户名或邮箱失败；不会提升现有账号权限，也不提供默认密码或密码命令行参数。

## 入口边界

bootstrap/cli 仅加载命令实际需要的配置、日志、资源，不导入 Web app。
命令复用 Service，不能直接写 SQL 或另写一套密码哈希。
create-superuser 通过明确的 Service 行为完成权限字段设置与事务，
交互密码不回显并确认输入；不把密码放日志。

doctor 保持只读，不创建数据库、目录、迁移或修改 .env 来掩盖问题。
SQLite 使用只读文件连接；缺失文件或内存数据库报告失败。
迁移检查比较数据库当前 heads 与项目 heads，未迁移或落后时提示显式升级。
Local 检查根目录和已存在的 public/private 目录及其权限，不试写；
新项目需显式创建 `STORAGE_LOCAL_ROOT`（默认 `data/storage`），doctor 不替用户创建。
权限检查不能代替真实上传验收。
public/private 子目录的符号链接或 Windows junction 会报告失败，与 Local Adapter 的路径规则一致。

已配置的 OSS/COS 使用对象存在性查询检查读取连接（不创建探测对象），
Redis 执行 PING 并关闭连接，Celery 仅连接 Broker，不发布任务或探测 Worker/结果后端。
禁用组件显示 disabled 且不导入其 SDK 或连接；已启用组件失败给出安全修复提示。
各资源检查独立报告，任一失败使 doctor 返回非零。

成功退出 0；业务、迁移或资源操作失败退出 1；非法用法、配置或输入退出 2。
中断交互退出 1。帮助和 version 不读取配置，不打开连接。
应用异常由 CLI 转为人类可读错误；默认不输出 traceback 或秘密。

## 验收与后续

`tests/integration/cli/` 验证安装入口、version、doctor 失败与只读行为、
真实 Alembic 生成/升级/降级、退出码、管理员创建、业务复用和提交失败回滚。
可选组件仅模拟 SDK/连接边界；测试用专门临时资源，不触及生产。

Template-first 通过 clone/use template 起步。
new、make module、make crud、shell、seed、项目自动升级和依赖安装命令
不属于 v0.1；未来生成器需先验证参考模块稳定，另行立项。
