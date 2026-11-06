# GD-SaiKen 组织级自动开发流水线设计

日期：2026-11-06

## 目标

1. 将 `1tang1315/IPQC` 迁移到 `GD-SaiKen/IPQC`，保留历史、Issue、标签和 Workflow。
2. 新建 `GD-SaiKen/auto-dev` 作为组织级中心仓库，集中维护可复用 Workflow、Kimi Code Prompt 和安装 Action。
3. IPQC 改为调用中心仓库；其他组织仓库复制 5 个薄触发器后即可使用，无需复制 Prompt 或 Agent 实现。

## 方案比较

| 方案 | 取舍 |
| --- | --- |
| 每个仓库复制完整 `.github/` 实现 | 接入直观，但 Prompt、修复和 Workflow 会随时间分叉，维护成本高 |
| 中心仓库可复用 Workflow + 业务仓库薄触发器（选定） | 逻辑集中、统一升级；业务仓库只需提供事件、参数和 Secret |
| GitHub App 集中监听所有仓库 | 可减少仓库内文件，但需要额外 App、私钥和常驻服务，超出当前需求 |

## 架构

```text
GD-SaiKen/auto-dev
  .github/workflows/auto-*.yml       # workflow_call 可复用实现
  .github/prompts/*.md               # 五类智能任务
  .github/actions/setup-kimi/        # CLI 安装
  .github/actions/run-prompt/        # 从中心 Action 目录读取 Prompt 并执行
  examples/consumer/.github/workflows/# 业务仓库接入模板

GD-SaiKen/IPQC 及其他业务仓库
  .github/workflows/auto-*.yml       # 仅事件触发、输入参数、权限、Secret 和中心仓库引用
```

### 调用链

- 业务仓库接收 `issues`、`push`、`pull_request` 和 `workflow_dispatch` 事件。
- 业务仓库通过 `workflow_call` 调用中心实现；`GITHUB_TOKEN`、Secrets 和 Variables 均属于业务仓库。
- develop → review → fix/merge 阶段通过业务仓库的 `workflow_dispatch` 显式调度，避免 `GITHUB_TOKEN` 二次事件抑制。
- 中心 Prompt 通过 `run-prompt` 复合 Action 的 `github.action_path` 读取，因此业务仓库不需要保存 Prompt 文件。

## 安全与兼容性

- 业务仓库只授予每个阶段所需的最小权限；只有 develop/review/fix 具有 `actions: write`。
- Secret `LLM_API_KEY` 由业务仓库显式传给中心可复用 Workflow，不写入中心仓库。
- 保留 `.github/` 防修改、fork PR 隔离、评审一致性、3 轮修复上限和 head SHA 原子合并校验。
- 中心引用默认使用 `@main` 便于组织内直接接入；生产环境可改为固定 tag 或 commit SHA。
- 组织与业务仓库必须允许 GitHub Actions 和可复用 Workflow；中心仓库设为 Public，避免私有共享策略阻断调用。

## 迁移与接入

1. 使用 GitHub Transfer API 将 IPQC 转移到组织，更新本地 `origin`。
2. 创建并推送 `GD-SaiKen/auto-dev`。
3. IPQC 用接入模板替换原有完整实现，推送后确认 5 个 Workflow active。
4. 其他仓库复制 `examples/consumer/.github/workflows/`，配置 `LLM_API_KEY` 并创建 `proposal`、`plan-ready`、`approved` 标签。

## 验证边界

- 验证中心与业务仓库 YAML、Bash、调用参数和远程 Workflow 注册。
- 若业务仓库没有 `LLM_API_KEY`，不声称真实模型调用或端到端闭环已验证。
