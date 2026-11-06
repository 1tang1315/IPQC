# IPQC

IPQC 已迁移到 `GD-SaiKen` 组织，并使用组织级中心仓库 [GD-SaiKen/auto-dev](https://github.com/GD-SaiKen/auto-dev) 提供的 AI 自动开发流水线。

本仓库只保留 5 个薄 Workflow，负责接收事件、传递参数和授权；方案、开发、评审、修复、合并的完整实现由中心仓库统一维护。

## 流程

```mermaid
flowchart LR
    A[Issue 带 proposal 标签<br/>或 proposals/*.md 推送] --> B[auto-plan<br/>生成开发方案]
    B --> C{人工审核<br/>加 approved 标签}
    C --> D[auto-develop<br/>Kimi Code 开发并测试]
    D --> E[提交 auto/ 分支 PR]
    E --> F[auto-review<br/>自动代码评审]
    F -- Approve --> G[auto-merge<br/>squash 合并 + 删除分支]
    F -- Request changes --> H[auto-fix<br/>自动修复并重新评审]
    H --> E
```

## 在 IPQC 中使用

1. 在仓库 **Settings → Secrets and variables → Actions** 配置 Secret `LLM_API_KEY`；
2. 新建 Issue 并加 `proposal` 标签，或推送 `proposals/*.md`；
3. 阅读机器人评论中的方案，审核通过后添加 `approved` 标签；
4. 后续开发、PR、评审、修复和合并自动执行；评审打回最多自动修复 3 轮。

可选 Variables：`LLM_MODEL`（默认 `kimi-for-coding`）、`LLM_BASE_URL`、`KIMI_CLI_VERSION`（默认 `latest`）。

## 在其他组织仓库中复用

复制中心仓库的 `examples/consumer/.github/workflows/` 下 5 个文件到目标仓库相同位置，保持文件名不变，然后：

1. 配置目标仓库的 `LLM_API_KEY`；
2. 创建 `proposal`、`plan-ready`、`approved` 标签；
3. 将方案文档放入 `proposals/`，或创建带 `proposal` 标签的 Issue。

详细接入说明见[中心仓库 README](https://github.com/GD-SaiKen/auto-dev#readme)。业务仓库不需要复制 Prompt 或安装 Action。

## 安全控制

- 业务仓库显式传递自己的模型 Secret，中心仓库不保存该 Key；
- 禁止 Agent 提交对 `.github/` 的修改；
- fork PR 不运行带模型凭据的评审；
- 只有 `auto/` 分支和机器人对当前 head SHA 的 Approved 评审可以进入自动合并；
- 合并 API 原子校验 head SHA，避免旧评审合入新提交。

## 版本引用

当前 5 个调用 Workflow 引用中心仓库 `@main`，会随中心更新。需要不可变版本时，可改成中心仓库的 release tag 或 commit SHA。

## 设计文档

- [组织级复用设计](docs/superpowers/specs/2026-11-06-org-auto-dev-design.md)
- [组织级实施计划](docs/superpowers/plans/2026-11-06-org-auto-dev.md)
- [初始流水线设计（历史）](docs/superpowers/specs/2026-11-05-auto-dev-pipeline-design.md)
