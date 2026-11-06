# Organization Auto-Dev Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 IPQC 迁移到 GD-SaiKen，并提供组织级中心仓库，使其他仓库仅复制薄触发器即可复用完整自动开发流水线。

**Architecture:** `GD-SaiKen/auto-dev` 提供 `workflow_call` 实现、Prompt 和复合 Action；业务仓库保留 5 个事件触发器并显式传递参数与 Secret。IPQC 自身也改用中心实现。

**Tech Stack:** GitHub Actions reusable workflows、composite actions、Kimi Code CLI、gh/git/jq、GitHub REST API。

**Spec:** `docs/superpowers/specs/2026-11-06-org-auto-dev-design.md`

## Global Constraints

- 中心仓库固定为 `GD-SaiKen/auto-dev`，业务仓库只保留薄 Workflow。
- 业务仓库的 `LLM_API_KEY` 必须显式传递，不写入中心仓库。
- 保留现有保护目录、fork 隔离、评审一致性、修复轮数和 head SHA 合并校验。
- 阶段间继续使用业务仓库内的显式 `workflow_dispatch`。
- 无 `LLM_API_KEY` 时只做静态与注册验证，不声称端到端成功。

## Review Focus

- 中心 Action 读取 Prompt 的路径必须相对 `github.action_path`，不能依赖业务仓库存在 Prompt。
- `workflow_call` 输入在 Issue、push、PR 和手动调度下必须类型一致，不得依赖缺省事件字段。
- 业务仓库调用权限必须允许中心 Workflow 所需操作，且中心不能提升权限。
- 显式调度必须作用于业务仓库而不是中心仓库。
- IPQC 迁移后本地 remote、Issue/标签历史和 Workflow 注册必须保持可用。

---

### Task 1: 迁移 IPQC 到组织

- [ ] 使用 `POST repos/1tang1315/IPQC/transfer`，`new_owner=GD-SaiKen`。
- [ ] 验证 `repos/GD-SaiKen/IPQC` 可读取，旧仓库 API 不再作为工作地址。
- [ ] 更新本地 `origin` 为 `git@github.com:GD-SaiKen/IPQC.git`，验证远程引用。

### Task 2: 创建组织中心仓库

**Files:** `.worktrees/auto-dev-central/`（独立本地仓库，推送到 `GD-SaiKen/auto-dev`）

- [ ] 复制现有 Prompt 和 setup-kimi Action，新增 `run-prompt` 复合 Action，用 `github.action_path` 定位中心 Prompt。
- [ ] 将 5 个 Workflow 改为 `workflow_call`，输入为 `issue_number`、`pr_number`、`expected_head_sha`、方案文档的 before/after SHA；Secret 仅声明 `LLM_API_KEY`。
- [ ] 创建 `examples/consumer/.github/workflows/` 五个薄调用模板和组织级 README。
- [ ] 静态检查所有 YAML、Bash 和输入/输出引用后创建公开组织仓库并推送。

### Task 3: IPQC 改用中心实现

**Files:** `G:\\workspace\\GD-SaiiKen\\IPQC` 的 `.github/` 与 README

- [ ] 删除 IPQC 内的中心实现副本，仅保留与 examples 一致的 5 个调用 Workflow。
- [ ] 更新 README，说明组织中心、复用方式、Secret 和版本引用。
- [ ] 静态检查中心引用均为 `GD-SaiKen/auto-dev/.github/workflows/auto-*.yml@main`，推送并确认 5 个 Workflow active。

### Task 4: 整体审查与交付

- [ ] 对中心仓库和 IPQC diff 做独立只读审查，修复 Critical/Important 问题并重复静态验证。
- [ ] 验证组织下两个仓库、默认分支和 IPQC 标签可用。
- [ ] 清理临时 worktree/分支，报告迁移结果、其他仓库接入步骤和未做的模型端到端验证。
