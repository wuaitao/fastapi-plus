# 贡献指南

先阅读 [AGENTS.md](AGENTS.md)、[当前里程碑](docs/roadmap.md)及相关主题文档。
当前为 M9 Release Hardening；v0.1 仅含 auth/user/file，后续功能须单独立项。

## 开发环境

安装 Python >= 3.11 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，
克隆仓库后在根目录执行：

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

`uv sync` 包含 dev 组；使用既有锁文件严格同步可执行 `uv sync --locked`。
无需配置 `.env`、数据库或外部服务。Ruff 同时承担 lint、import 排序和格式化。

编辑后执行 `uv run ruff format .`。若希望直接运行质量命令，先激活环境：

```powershell
# Windows PowerShell
. .venv/Scripts/Activate.ps1
```

```bash
# POSIX shell
source .venv/bin/activate
```

随后运行 `ruff check .`、`ruff format --check .`、`pyright`、`pytest`。

## 发布验证

普通测试使用临时 SQLite，不需要 Docker、外部数据库、云账号或 Worker 服务。
发布前还须执行 [覆盖率门槛](docs/testing.md#发布质量)及
[三数据库在线矩阵](docs/release.md#三数据库在线验证)：同一测试文件验证真实迁移、事务、
并发唯一约束、Auth/User/File 流程。外部数据库必须为专用空库，名称以 `fastplus_test_` 开头；
测试执行降级并清理表，绝不使用开发或生产库。缺少配置时失败，不用 skip 冒充通过。

运行数据库矩阵时用对应 `uv run --extra postgresql` 或 `--extra mysql` 保留驱动。
不要在正在执行测试的环境中运行会移除 extras 的 `uv sync`。
记录操作系统、Python/服务器/驱动版本和真实结果；未覆盖的平台、云联调和发布阻塞项
写入 [发布验收](docs/release.md)。新增行为同步 CHANGELOG，正式发布前使用干净检出验证 README。

## 开发规则

- 保持 Router → Service → Repository / Provider → Infrastructure 方向。
- Router 负责 HTTP，Service 负责业务与 commit/rollback，Repository 永不 commit。
- Service 返回 ORM / 应用结果，Router 转换 API Schema；厂商 SDK 留在 Adapter。
- 完整类型标注；非显而易见的逻辑使用中文注释说明原因。
- 行为变更须有测试；使用真实边界测试被测组件，不修改无关代码。
- 新依赖须说明标准库和现有依赖为何不足、所属里程碑、维护及平台成本。
  运行时与开发依赖分开；不提前安装可选基础设施，不增加重复工具。
- 依赖变更同步提交 `pyproject.toml` 与 `uv.lock`，升级后运行适用质量检查。
  具体 uv 依赖操作参见 [官方文档](https://docs.astral.sh/uv/concepts/projects/dependencies/)。
- 模型变更附迁移；公开契约变更同步文档与测试。

## 提交与 PR

采用 Conventional Commits：`type(scope): description`，例如
`docs(architecture): clarify transaction ownership` 或
`chore(tooling): configure repository checks`。常用类型为 feat、fix、docs、test、refactor、chore。

PR 描述说明问题、最终行为和验证结果。清单：

- [ ] 仅包含当前任务所需变更，无功能或架构扩张。
- [ ] 类型与中文说明完整，行为测试充分。
- [ ] 新依赖有明确理由，锁文件一致。
- [ ] 需要的迁移、API/OpenAPI 和文档已同步。
- [ ] Ruff lint/format、Pyright、Pytest 通过。
- [ ] 发布时三数据库在线矩阵和覆盖率门槛通过，OpenAPI 与实际响应一致。
- [ ] README、相关主题文档和 CHANGELOG 已同步，未引入 Docker/前端耦合或额外业务范围。
- [ ] 未加入真实秘密、默认凭据或运行数据。
- [ ] 已审查完整差异并如实说明尚未验证的边界。
