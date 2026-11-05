# IPQC 仓库自动开发流水线 — 设计文档

日期：2026-11-05
状态：已实现（本文档与代码同批次提交）

## 意图与背景

用户希望基于 GitHub 仓库实现一条"方案 → 开发 → 评审 → 合并"的自动开发流水线：

1. 自动发现仓库中的新增方案文档（`proposals/*.md`）和带 `proposal` 标签的 Issue，并由 AI 生成开发方案；
2. 人工审核方案（给 Issue 加 `approved` 标签）后，AI 按方案中的任务拆分自动开发代码，完成后提交 PR；
3. 对新提交的 PR 自动进行 AI code review（提交 Approve 或 Request changes 评审）；
4. 评审通过后自动合并 PR（squash）并删除开发分支；被打回时自动修复并再次提交评审，形成闭环。

## 目标 / 非目标 / 反目标

- 目标：上述 4 步全自动闭环；全部逻辑版本化在仓库内；对任意 OpenAI 兼容模型Provider 可配置。
- 非目标：不做对话式机器人（不响应 `/command` 评论命令）；v1 不做行内（inline）评审评论，评审以 PR Review（Approve / Request changes）形式给出。
- 反目标：绝不让 AI 修改 `.github/workflows/` 与 `.github/scripts/`（流水线自身）；绝不自动合并非 `auto/` 前缀分支的 PR（人工 PR 只做评审，不做合并）。

## 候选方案（Approaches）

| 方案 | 说明 | 取舍 |
| --- | --- | --- |
| A. GitHub Actions + LLM API（**选定**） | 5 个 workflow + Python 脚本，事件驱动，代码全部在仓库内 | 与 GitHub 原生集成（用户明确要求"基于 GitHub 仓库"）；无需常驻服务器；缺点：单 job 最长 6 小时，超长任务需拆分方案 |
| B. 自托管常驻 Agent（如 Kimi Code CLI 轮询） | 本地/服务器跑 Agent 监听仓库事件 | 依赖机器常开、网络与凭据管理；不符合"基于 GitHub"的诉求 |
| C. 第三方平台（Devin / OpenHands / Copilot coding agent） | 托管服务 | 引入外部依赖与费用，可控性与可审计性差 |

选定 A：事件驱动、透明、可审计，且完全落在仓库内。

## 架构

```
Issue(proposal 标签) 或 proposals/*.md 推送
        │
        ▼
auto-plan ──AI 生成方案──► 方案以评论形式发到 Issue，加 plan-ready 标签
        │
        ▼  人工审核：加 approved 标签
auto-develop ──AI 读方案、逐任务改代码──► 推送 auto/issue-<n>-<slug> 分支，创建 PR（Closes #n）
        │
        ▼
auto-review ──AI 评审 diff──► Approve 或 Request changes（GitHub PR Review）
        │                         │
        │ Approve                 │ Request changes
        ▼                         ▼
auto-merge ◄────────────── auto-fix：AI 按评审意见修复、推送
 squash 合并 + 删除分支        （触发 synchronize → 重新评审，最多 3 轮）
```

### 组件

- `.github/auto-dev.json`：流水线配置（标签名、分支前缀、默认模型、测试命令、受保护路径、修复轮数上限）。
- `.github/scripts/ai.py`：OpenAI 兼容 LLM 客户端 + 受限文件工具（list_files / read_file / write_file，禁止越出仓库、禁止写受保护路径）+ agent 工具循环。
- `.github/scripts/generate_plan.py`：方案生成（Issue 模式 / 提案文档模式）。
- `.github/scripts/develop.py`：自动开发：取方案 → agent 实现全部任务 → 可选测试命令验证失败自动修复 → 提交分支与 PR。
- `.github/scripts/review_pr.py`：AI 评审，输出结构化 JSON 结论，提交 PR Review。
- `.github/scripts/fix_pr.py`：AI 按 Request changes 评审意见修复并推送（带轮数上限保险）。
- 5 个 workflow：auto-plan / auto-develop / auto-review / auto-fix / auto-merge。

### 关键机制与护栏

- **审核闸口**：方案生成后只是评论 + 标签，必须人工加 `approved` 标签才开发；这是全流程唯一必需的人工动作。
- **自动合并闸口**：仅当 `head.ref` 以 `auto/` 开头、且 Approve 评审者是 `github-actions[bot]` 时才自动合并；非机器人评审通过不触发合并。
- **自修改防护**：AI 文件工具拒绝写入 `protectedPaths`（默认 `.github/workflows/`、`.github/scripts/`）。
- **防死循环**：自动修复最多 `maxReviewRounds`（默认 3）轮，超限后留言转人工；agent 单轮数与文件大小均设上限。
- **幂等**：重复触发 plan 不会重复生成；develop 重复触发会复用已存在的分支与 PR 并更新。

## LLM 配置

- Provider：Kimi Code API（OpenAI 兼容），Base URL 默认 `https://api.kimi.com/coding/v1`（海外 `https://api.kimi.ai/coding/v1`），默认模型 `kimi-for-coding`。
- 凭据：仓库 Secret `LLM_API_KEY`（在 Kimi Code 控制台创建）；可用仓库 Variables `LLM_BASE_URL` / `LLM_MODEL` 覆盖。
- 亦兼容任意 OpenAI 兼容端点（换 Base URL 与 Key 即可）。

## 我做的决定（Assumptions / Calls）

- 仓库可见性为 Public（用户已确认）；流水线不处理机密代码场景。
- 方案/评审语言：跟随 Issue 语言，提示词以中文编写。
- 合并策略：squash，保持 main 历史干净。
- 测试命令默认未配置；在 `.github/auto-dev.json` 的 `testCommand` 配置后，develop 阶段会自动运行并在失败时让 AI 修复。
- PR Review 采用整体评审（summary + findings），不做行内评论（后续增强项）。

## 参考

- Kimi Code 文档（API 接入 / 模型列表）：https://www.kimi.com/code/docs/en/
