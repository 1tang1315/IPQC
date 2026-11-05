# IPQC 仓库自动开发流水线 — 设计文档

日期：2026-11-05
状态：Kimi Code CLI 版已实现

## 意图与背景

基于 GitHub 仓库实现一条“方案 → 开发 → 评审 → 合并”的自动开发流水线：

1. 自动发现仓库中的新增方案文档（`proposals/*.md`）和带 `proposal` 标签的 Issue，并由 AI 生成开发方案；
2. 人工审核方案（给 Issue 加 `approved` 标签）后，AI 按方案中的任务拆分自动开发代码，完成后提交 PR；
3. 对新提交的 PR 自动进行 AI code review（提交 Approve 或 Request changes 评审）；
4. 评审通过后自动合并 PR（squash）并删除开发分支；被打回时自动修复并再次提交评审，形成闭环。

## 目标 / 非目标 / 反目标

- 目标：全流程事件驱动；复用 Kimi Code 的代码阅读、编辑、命令执行和测试修复能力；编排逻辑全部版本化。
- 非目标：不做对话式评论机器人；不做行内评审评论；不维护自写的 LLM 工具循环。
- 反目标：不允许 AI 修改 `.github/`；不自动合并非 `auto/` 前缀分支的 PR；不向 fork PR 暴露模型凭据。

## 候选方案（Approaches）

| 方案 | 说明 | 取舍 |
| --- | --- | --- |
| A. GitHub Actions + Kimi Code CLI（**选定**） | Workflow 编排，`kimi -p` 执行智能任务，gh/git 完成确定性操作 | 复用完整 Agent 能力，无需自写 Agent；runner 需安装 CLI，非交互模式自动执行工具 |
| B. GitHub Actions + Python + LLM API | 自写 LLM 客户端、文件工具和 Agent 循环 | 通用、依赖少，但重复实现 Agent，代码能力和维护性较弱；本版移除 |
| C. 本机常驻 Agent 轮询 | 当前 Desktop/CLI 会话定时检查仓库 | 依赖机器和会话在线，不是可靠的 GitHub 事件消费者 |

选定 A：最符合“Workflow + 当前 Agent 机制”的目标，同时保留 GitHub 原生的事件、权限和审计能力。

## 架构

```text
Issue(proposal 标签) 或 proposals/*.md 推送
        │
        ▼
auto-plan ──kimi -p 生成方案──► Issue 评论 + plan-ready 标签
        │
        ▼  人工审核：加 approved 标签
auto-develop ──kimi -p 实现并测试──► Workflow 校验、提交、推送、创建 PR
        │
        ▼
auto-review ──kimi -p 输出结构化评审──► Workflow 提交 PR Review
        │                         │
        │ Approve                 │ Request changes
        ▼                         ▼
auto-merge ◄────────────── auto-fix：kimi -p 修复，Workflow 校验并推送
 squash 合并 + 删除分支        （触发 synchronize → 重新评审，最多 3 轮）
```

### 组件

- `.github/actions/setup-kimi/action.yml`：复合 Action，安装 Node.js 22 与 `@moonshot-ai/kimi-code`，校验 CLI 和 API Key。
- `.github/prompts/plan-issue.md`：从 Issue 生成方案并发布评论。
- `.github/prompts/plan-doc.md`：从方案文档生成方案，创建或更新对应 Issue。
- `.github/prompts/develop.md`：读取已审核方案，实现任务、运行测试并写实现摘要。
- `.github/prompts/review.md`：评审 PR，写结构化 JSON 到 runner 临时目录。
- `.github/prompts/fix.md`：按最新打回评审修复代码并写修复摘要。
- `.github/workflows/`：5 个事件驱动 Workflow，负责触发、分支、校验、提交、评审发布和合并。

## 关键机制与护栏

- **审核闸口**：只有人工添加 `approved` 标签才进入开发。
- **自动合并闸口**：仅 `auto/` 分支、`github-actions[bot]` 的 Approved 评审可触发；等待检查通过后 squash 合并并删分支。
- **自修改防护**：Prompt 禁止修改 `.github/`，Workflow 在提交前再次用 Git diff 强制检查；命中即失败，不推送。
- **防空提交**：开发和修复没有文件变更时只留言，不创建空提交或 PR。
- **防死循环**：最多自动修复 3 轮；第 4 次被机器人 Request changes 打回时停止修复并转人工。
- **幂等**：已有机器人方案评论时跳过 Issue 方案生成；开发复用 `auto/issue-<n>` 分支和已有 PR。
- **fork 安全**：只评审与目标仓库同源的 PR；fork PR 不启动带模型 Secret 的 Agent。

## LLM 与 CLI 配置

- Secret：`LLM_API_KEY` 映射为 `KIMI_MODEL_API_KEY`。
- Variables：`LLM_BASE_URL`（默认 `https://api.kimi.com/coding/v1`）、`LLM_MODEL`（默认 `kimi-for-coding`）、`KIMI_CLI_VERSION`（默认 `latest`，生产使用建议固定版本）。
- CLI 使用 `kimi -p` 非交互模式；该模式默认自动执行常规工具，因此 Workflow 使用最小权限并保留确定性安全检查。

## 我做的决定（Assumptions / Calls）

- 开发分支统一为 `auto/issue-<n>`，不再从可能包含中文的标题生成 slug。
- AI 自行识别并运行项目现有测试；没有测试时进行与项目匹配的构建或静态检查。
- 评审采用整体 PR Review（summary + findings），不做行内评论。
- 固定保护整个 `.github/` 目录；最大自动修复轮数固定为 3，均可在 Workflow 中直接调整。

## 参考

- CLI 安装：https://www.kimi.com/code/docs/en/kimi-code-cli/guides/getting-started.html
- 非交互命令：https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command.html
- CI 环境变量：https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/env-vars.html
