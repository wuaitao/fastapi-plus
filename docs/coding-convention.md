# 编码与依赖规范

本规范从 M0 起适用；运行时示例涉及的能力按 [roadmap](roadmap.md) 实现。

## Python 与风格

- Python >= 3.11；源码语法与类型检查最低目标均为 3.11。
- Ruff 负责 lint、import 排序和格式化；行宽 100，四空格缩进、双引号。
- Pyright 是唯一主类型检查器，当前启用 strict；Pytest 是测试框架。
- 文件、函数、变量使用 snake_case，类使用 PascalCase，常量使用 UPPER_SNAKE_CASE。
- 函数参数、返回值与公共接口完整标注类型，优先标准 typing 和内建容器类型。
- 非显而易见的逻辑用清晰中文注释解释原因，特别是事务、补偿、资源作用域与安全边界。
  不用注释复述显然可见的语句。
- 不增加未使用的抽象；仅修改任务必需内容，匹配既有风格。

配置详见 [pyproject.toml](../pyproject.toml)；
工具配置参考 [Ruff](https://docs.astral.sh/ruff/configuration/)、
[Pyright](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)。

## 模块与数据边界

分层以 [architecture](architecture.md) 为准。业务按模块组织，不设全局业务
models/schemas/services/routers。Model 描述数据库结构，不承载工作流。

Schema 表达输入意图；创建、PATCH 和输出分开。PATCH 区分“未提供”与显式 null，
敏感字段不进入万能更新。Repository 返回 ORM，Service 返回 ORM/应用结果，
Router 序列化为 API Schema。模块错误描述符与依赖函数留在模块内。

I/O 使用异步接口；同步 SDK 的阻塞调用由 Adapter 隔离。
不在异步路径调用阻塞 sleep，不在各任务中散布异步桥接。
业务日志使用 structlog 结构化事件，不用 print 或自由文本代替事件字段。

## 依赖政策

每次新增依赖必须有当前任务的具体理由，并检查：

1. 标准库或现有依赖是否已足够。
2. 是否属于当前里程碑、是否值得进入核心路径。
3. 维护状态、Python 兼容性、许可证与跨平台风险。
4. 传递依赖规模与长期升级成本。

`pyproject.toml` 是依赖声明的唯一来源，`uv.lock` 固定验证版本。
采用合理版本范围，不使用无约束“latest”，不再维护平行 requirements 清单。
开发依赖放 dev 组，运行时依赖按功能落地逐步添加。

M1 运行时依赖为 FastAPI、Pydantic、pydantic-settings 和 Uvicorn；
开发依赖为 Ruff、Pyright、Pytest、pytest-asyncio 和用于 API 测试的 HTTPX。
setuptools 仅作为标准构建后端。uv 是外部开发工具，不是应用依赖。
M9 使用开发依赖 coverage.py 测量语句与分支覆盖率；不增加运行时依赖或重复测试框架。
标准库没有现成的覆盖率报告/门槛工具，现有 Pytest 也不提供该能力。
coverage.py 采用 Apache-2.0，支持 Python >= 3.11，锁文件包含主流平台 wheel；
具体版本由 uv.lock 固定，报告命令见 [testing](testing.md#发布质量)。

Redis、Celery、OSS/COS SDK、MySQL/PostgreSQL 驱动按对应里程碑加入可选安装集合。
不提前定义虚假的 extras，也不提供默认全量安装。
HTTPX 等库仅在实际测试或运行时调用需要时引入，不因“以后常用”预装。

禁止重复维护 Black、isort、flake8、Mypy、Loguru、Poetry，
或引入多个 JWT 库、ORM 抽象、重试框架来重复已有能力。

## 升级与提交

依赖变更同时更新声明与锁文件，执行质量检查；大版本升级查阅迁移说明，
覆盖受影响的参考模块、数据库矩阵与 Provider 契约。
第三方无类型 SDK 的弱类型限制在 Adapter，不用广泛 ignore/noqa 隐藏问题。

开发命令、Conventional Commits 和 PR 清单见 [CONTRIBUTING](../CONTRIBUTING.md)。
