# Kimi Code CLI Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Python 自写 Agent 流水线重构为 GitHub Actions 编排、Kimi Code CLI 执行、gh/git 完成确定性操作的流水线。

**Architecture:** 复合 Action 统一安装 CLI；五个版本化 Prompt 负责智能任务；五个 Workflow 负责事件、权限、分支、校验、提交、评审发布和合并。删除 Python Agent 与 JSON 配置。

**Tech Stack:** GitHub Actions YAML、Bash、Kimi Code CLI、gh、git、jq。

**Spec:** `docs/superpowers/specs/2026-11-05-auto-dev-pipeline-design.md`

## Global Constraints

- 不保留 `.github/scripts/` 中的 Python Agent 或 `.github/auto-dev.json`。
- AI 不得修改 `.github/`；提交前必须用 Git diff 强制校验。
- 自动合并只接受 `auto/` 分支和 `github-actions[bot]` 的 Approved 评审。
- fork PR 不运行带模型 Secret 的自动评审。
- 项目没有测试套件，不新增测试脚手架；使用 YAML 解析、静态检查和 GitHub workflow 注册状态验证。

## Review Focus

- 重复添加 `proposal` 标签：不得重复发布方案评论，由 auto-plan 的存在性检查覆盖。
- `proposals/README.md` 或首次推送：不得把目录说明当需求，由文档过滤和全零 SHA 分支覆盖。
- Agent 未产生变更或试图修改 `.github/`：不得空提交或推送受保护变更，由 auto-develop/auto-fix 校验覆盖。
- fork PR：不得读取模型 Secret，由 auto-review 的同源仓库条件覆盖。
- 连续评审打回：最多自动修复 3 轮，由 auto-fix 的评审计数覆盖。

---

### Task 1: Kimi CLI 安装复合 Action

**Files:**
- Create: `.github/actions/setup-kimi/action.yml`

**Interfaces:**
- Consumes: Job env `KIMI_MODEL_API_KEY`；input `version`。
- Produces: 后续 step 可直接运行 `kimi -p`；Node.js 22 与 CLI 已安装。

- [ ] 创建复合 Action：使用 `actions/setup-node@v4` 安装 Node 22，按 input 安装 `@moonshot-ai/kimi-code`，检查 API Key 非空并执行 `kimi --version`。
- [ ] 用 PyYAML 仅作本地 YAML 解析校验，确认文件可解析且 `runs.using` 为 `composite`。

### Task 2: 方案生成 Prompt 与 auto-plan

**Files:**
- Create: `.github/prompts/plan-issue.md`
- Create: `.github/prompts/plan-doc.md`
- Modify: `.github/workflows/auto-plan.yml`

**Interfaces:**
- Consumes: `ISSUE_NUMBER` 或 `PROPOSAL_PATH`、`GH_TOKEN`、Kimi 模型环境变量。
- Produces: 带 `<!-- auto-dev-plan -->` 的 Issue 评论及 `plan-ready` 标签。

- [ ] 编写两个只读代码、只对方案 Issue 有写操作的 Prompt，固定方案章节和 3~7 个任务清单。
- [ ] 重写 Workflow：Issue 模式跳过已有机器人方案；文档模式过滤 `proposals/README.md`、处理全零 before SHA，并逐文档调用对应 Prompt。
- [ ] 解析 YAML，并静态确认两个模式均使用 `kimi -p` 和安装复合 Action。

### Task 3: 自动开发 Prompt 与 auto-develop

**Files:**
- Create: `.github/prompts/develop.md`
- Modify: `.github/workflows/auto-develop.yml`

**Interfaces:**
- Consumes: 最新带 `PLAN_MARKER` 的方案评论、`ISSUE_NUMBER`。
- Produces: `auto/issue-<n>` 分支、非空提交、创建或更新 PR，并评论关联 Issue。

- [ ] 编写开发 Prompt：实现全部任务、识别并运行现有测试、禁止 `.github/` 变更、将摘要写入 runner 临时文件，不自行提交。
- [ ] 重写 Workflow：准备/复用分支，运行 CLI；检测空变更；阻止 `.github/` 变更；由 git/gh 提交、推送、创建或更新 PR。
- [ ] 解析 YAML，静态确认无 Python 调用且保护与空变更分支均存在。

### Task 4: 自动评审、修复与合并

**Files:**
- Create: `.github/prompts/review.md`
- Create: `.github/prompts/fix.md`
- Modify: `.github/workflows/auto-review.yml`
- Modify: `.github/workflows/auto-fix.yml`
- Modify: `.github/workflows/auto-merge.yml`（仅必要时）

**Interfaces:**
- Consumes: PR diff 和最新机器人 Request changes 评审。
- Produces: review JSON → GitHub PR Review；修复提交 → synchronize 重新评审；Approved → squash 合并并删分支。

- [ ] 编写评审 Prompt，固定 JSON schema：`verdict`、`summary`、`findings`；编写修复 Prompt，要求逐项处理并运行测试。
- [ ] 重写 auto-review：跳过 draft 和 fork PR，校验 JSON，使用 gh 提交 Approve/Request changes。
- [ ] 重写 auto-fix：最多 3 次机器人打回，复用开发和保护校验；保留 auto-merge 的确定性条件。
- [ ] 解析所有 YAML，并静态检查 merge/fix 的触发条件。

### Task 5: 删除旧实现、更新文档并交付

**Files:**
- Delete: `.github/scripts/ai.py`、`generate_plan.py`、`develop.py`、`review_pr.py`、`fix_pr.py`
- Delete: `.github/auto-dev.json`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-05-auto-dev-pipeline-design.md`

**Interfaces:**
- Produces: 仓库文档、目录和实际 CLI 实现一致。

- [ ] 删除旧 Python/JSON 实现，更新 README 的配置、使用、安全和目录说明。
- [ ] 全仓检查不再引用 `.github/scripts` 或 `auto-dev.json`，所有 YAML/JSON/Markdown 链接有效。
- [ ] 提交并推送，使用 GitHub API 确认五个 workflow 为 active；创建 `proposal`、`plan-ready`、`approved` 标签。
- [ ] 记录未能端到端验证的部分：若仓库未配置 `LLM_API_KEY`，不得声称实际模型调用已验证。
