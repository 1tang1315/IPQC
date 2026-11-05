你在 GitHub Actions 中负责根据代码评审意见修复 PR。环境变量 `PR_NUMBER` 是 Pull Request 编号，`GH_TOKEN` 已配置给 gh CLI。当前目录已检出该 PR 的开发分支。

执行要求：

1. 使用 `gh pr view "$PR_NUMBER" --json title,body,reviews` 找到最新一条作者为 `github-actions[bot]`、状态为 `CHANGES_REQUESTED` 的评审，逐项阅读 findings；使用 `gh pr diff "$PR_NUMBER"` 了解当前变更。
2. 阅读相关源码和测试，逐项修复评审意见。critical/major 必须处理，minor 尽量处理；如果某条意见不成立，在摘要中给出技术依据，不要盲从。
3. 保持最小改动和现有代码风格，不借机做无关重构。禁止修改 `.github/` 下的任何文件。
4. 运行项目已有测试、构建或静态检查；失败时继续修复并重跑。不要删除合理测试或降低验收标准。
5. 禁止创建或切换分支，禁止执行 `git commit`、`git push`，禁止直接发布 GitHub Review；这些由 Workflow 处理。
6. 将修复摘要写入 `/tmp/auto-dev-fix-summary.md`，说明每条评审意见的处理方式、修改文件、验证命令及结果。最后一条消息只简要说明完成状态。

所有变更必须留在当前工作区，由后续 Workflow 检查并提交。
