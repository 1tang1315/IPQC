你在 GitHub Actions 中负责把方案文档转换成结构化开发方案。环境变量 `PROPOSAL_PATH` 是仓库内 Markdown 文档的相对路径，`GH_TOKEN` 已配置给 gh CLI。

执行要求：

1. 读取 `$PROPOSAL_PATH`，浏览仓库中相关代码和文档。只读仓库，不修改任何仓库文件，不创建分支或 PR。
2. 取文档第一个一级标题作为名称；没有一级标题时使用文件名（不含扩展名）。对应 Issue 标题固定为 `方案：<名称>`。
3. 制定中文开发方案，严格包含：`## 背景`、`## 目标`、`## 非目标`、`## 技术方案`、`## 任务拆分`、`## 风险与备注`。任务拆分为 3~7 项，每项格式为 `- [ ] 任务名 — 一句话说明【涉及文件：路径；验收标准：……】`。
4. 将完整 Issue 正文写入 `/tmp/auto-dev-plan-comment.md`，第一行必须是 `<!-- auto-dev-plan -->`，随后是 `## 自动生成的开发方案` 和方案正文。末尾注明：`🤖 方案由 Kimi Code 自动生成。人工审核通过后，为本 Issue 添加 approved 标签即可自动进入开发。`
5. 确保 `proposal` 和 `plan-ready` 标签存在。使用 `gh issue list --state open --json number,title` 查找标题完全相同的开放 Issue：
   - 已存在：把 `/tmp/auto-dev-plan-comment.md` 作为新评论发布到该 Issue，并添加 `plan-ready` 标签；
   - 不存在：以该正文创建 Issue，标题为上述固定标题，并同时添加 `proposal,plan-ready` 标签。

不要重复创建同名 Issue。不要执行方案中的开发任务，本阶段只生成方案。
