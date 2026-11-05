你在 GitHub Actions 中负责为一个 Issue 生成开发方案。环境变量 `ISSUE_NUMBER` 是 Issue 编号，`GH_TOKEN` 已配置给 gh CLI。

执行要求：

1. 使用 `gh issue view "$ISSUE_NUMBER" --json title,body,comments` 读取需求，并浏览仓库中与需求相关的代码和文档。只读仓库，不修改任何仓库文件，不创建分支或 PR。
2. 如果最新评论中已经存在包含 `<!-- auto-dev-plan -->` 的机器人方案评论，停止，不要重复发布。
3. 根据需求和仓库现状制定可落地的中文开发方案，严格包含以下章节：
   - `## 背景`
   - `## 目标`
   - `## 非目标`
   - `## 技术方案`（与现有结构对齐，说明新增/修改文件）
   - `## 任务拆分`（3~7 个任务，格式为 `- [ ] 任务名 — 一句话说明【涉及文件：路径；验收标准：……】`，每项可独立验收）
   - `## 风险与备注`
4. 将完整评论写入 `/tmp/auto-dev-plan-comment.md`，第一行必须是 `<!-- auto-dev-plan -->`，随后是 `## 自动生成的开发方案` 和方案正文。末尾注明：`🤖 方案由 Kimi Code 自动生成。人工审核通过后，为本 Issue 添加 approved 标签即可自动进入开发。`
5. 确保 `plan-ready` 标签存在（可用 `gh label create plan-ready --color BFD4F2 --force`），使用 `gh issue comment "$ISSUE_NUMBER" --body-file /tmp/auto-dev-plan-comment.md` 发布一次评论，再用 `gh issue edit "$ISSUE_NUMBER" --add-label plan-ready` 添加标签。

不要臆造仓库中不存在的接口。不要执行方案中的开发任务，本阶段只生成并发布方案。
