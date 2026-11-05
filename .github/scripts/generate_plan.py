"""auto-plan：为需求生成开发方案。

两种触发方式（由 workflow 注入环境变量决定）：
- ISSUE_NUMBER  ：为指定 Issue 生成方案，以评论形式发布；
- PROPOSAL_PATH ：为 proposals/ 下的方案文档生成方案，并创建对应 Issue（已存在同名
                  开放 Issue 时改为追加重发，避免重复）。
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai import (  # noqa: E402
    ROOT,
    PLAN_MARKER,
    chat,
    ensure_label,
    gh,
    load_config,
    repo_tree,
)

PLAN_SYSTEM = """你是资深软件架构师，为代码仓库制定可落地的开发方案。 \
严格输出 Markdown，不要输出任何与方案无关的内容。方案必须包含以下章节：

## 背景
## 目标
## 非目标
## 技术方案
（与仓库现有结构对齐；说明新增/修改的文件）
## 任务拆分
（格式：- [ ] 任务名 — 一句话说明【涉及文件：路径；验收标准：……】；拆成 3~7 个任务，每个任务可独立验收）
## 风险与备注
"""

PLAN_HINT = (
    "\n\n---\n🤖 方案由 auto-dev 工作流自动生成。人工审核通过后，"
    "为本 Issue 添加 `approved` 标签即可自动进入开发。"
)


def cfg_label(key, default):
    return load_config().get("labels", {}).get(key, default)


def gen_plan(requirement):
    user = (
        "请为下面的需求制定开发方案。\n\n## 需求\n"
        + requirement
        + "\n\n## 仓库现有结构\n```\n"
        + repo_tree()
        + "\n```\n"
    )
    msg = chat(
        [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": user}],
        max_tokens=8000,
    )
    return (msg.get("content") or "").strip()


def find_bot_plan(issue):
    for c in reversed(issue.get("comments", [])):
        body = c.get("body") or ""
        author = (c.get("author") or {}).get("login", "")
        if PLAN_MARKER in body and author == "github-actions[bot]":
            return body
    return None


def plan_from_issue(number):
    issue = json.loads(
        gh("issue", "view", number, "--json", "title,body,comments,labels")
    )
    if find_bot_plan(issue):
        print(f"issue #{number} 已有方案评论，跳过重复生成")
        return
    requirement = f"标题：{issue['title']}\n\n{issue.get('body') or '（无正文）'}"
    plan = gen_plan(requirement)
    if not plan:
        raise RuntimeError("LLM 未返回方案内容")
    plan_ready = cfg_label("planReady", "plan-ready")
    ensure_label(plan_ready)
    body = f"{PLAN_MARKER}\n## 自动生成的开发方案\n\n{plan}{PLAN_HINT}"
    gh("issue", "comment", number, "--body-file", "-", input_text=body)
    gh("issue", "edit", number, "--add-label", plan_ready)
    print(f"issue #{number}: plan posted")


def find_open_issue_by_title(title):
    out = gh("issue", "list", "--state", "open", "--json", "number,title", check=False)
    try:
        issues = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    for it in issues:
        if it["title"] == title:
            return it["number"]
    return None


def plan_from_doc(path):
    p = ROOT / path
    if not p.is_file():
        print(f"skip missing file: {path}")
        return
    content = p.read_text(encoding="utf-8", errors="replace")
    heading = None
    for line in content.splitlines():
        m = re.match(r"^#\s+(.+)", line.strip())
        if m:
            heading = m.group(1).strip()
            break
    title = "方案：" + (heading or Path(path).stem)
    plan = gen_plan(f"方案文档 `{path}` 内容如下：\n\n{content}")
    if not plan:
        raise RuntimeError("LLM 未返回方案内容")

    proposal_label = cfg_label("proposal", "proposal")
    plan_ready = cfg_label("planReady", "plan-ready")
    ensure_label(proposal_label)
    ensure_label(plan_ready)

    body = f"{PLAN_MARKER}\n## 自动生成的开发方案\n\n{plan}{PLAN_HINT}"
    existing = find_open_issue_by_title(title)
    if existing:
        gh("issue", "comment", existing, "--body-file", "-", input_text=body)
        gh("issue", "edit", existing, "--add-label", plan_ready)
        print(f"issue #{existing}: plan re-posted for doc {path}")
    else:
        gh(
            "issue",
            "create",
            "--title",
            title,
            "--body-file",
            "-",
            "--label",
            f"{proposal_label},{plan_ready}",
            input_text=body,
        )
        print(f"created issue for doc {path}")


def main():
    issue_number = os.environ.get("ISSUE_NUMBER")
    proposal_path = os.environ.get("PROPOSAL_PATH")
    if issue_number:
        plan_from_issue(issue_number)
    elif proposal_path:
        for path in proposal_path.split():
            if path.endswith(".md"):
                plan_from_doc(path)
    else:
        raise SystemExit("ISSUE_NUMBER 或 PROPOSAL_PATH 必须设置一个")


if __name__ == "__main__":
    main()
