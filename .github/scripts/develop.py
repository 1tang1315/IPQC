"""auto-develop：读取已审核的方案（Issue 中带 PLAN_MARKER 的评论），
由 AI 按任务清单实现全部代码，提交到 auto/ 分支并创建（或更新）PR。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai import (  # noqa: E402
    ROOT,
    PLAN_MARKER,
    continue_agent,
    gh,
    last_assistant_text,
    load_config,
    repo_tree,
    run_agent,
    slugify,
)

DEVELOPER_SYSTEM = """你是资深开发工程师，在 CI 环境中自动完成开发任务。你会拿到一份已经过人工审核的开发方案。

工作要求：
1. 先用工具浏览仓库、阅读与方案相关的现有代码，理解现有结构与约定。
2. 严格按方案"任务拆分"清单逐一实现全部任务，不要遗漏，也不要扩大范围。
3. 遵循仓库现有代码风格、命名与目录约定；不要引入与方案无关的重构。
4. 禁止臆造不存在的 API/文件，不确定的地方先 read_file 确认。
5. 不要修改 .github/ 下的工作流与脚本（受保护路径）。
6. 全部任务完成后，用最后一条消息输出实现摘要：完成了什么、修改/新增了哪些文件、每个任务如何验收。不要在最终消息里贴大段代码。
"""


def sh(args, check=True, timeout=900):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
        )
    return r


def find_plan(issue):
    for c in reversed(issue.get("comments", [])):
        if PLAN_MARKER in (c.get("body") or ""):
            return c["body"].split(PLAN_MARKER, 1)[1].strip()
    return None


def run_tests(test_cmd, max_fix_rounds, messages):
    """运行配置的测试命令；失败时把输出喂回给 agent 修复，最多 max_fix_rounds 轮。"""
    for i in range(max_fix_rounds + 1):
        r = subprocess.run(
            test_cmd, shell=True, capture_output=True, text=True, timeout=900, cwd=str(ROOT)
        )
        if r.returncode == 0:
            return True, ""
        output = ((r.stdout or "") + "\n" + (r.stderr or ""))[-6000:]
        if i >= max_fix_rounds:
            return False, output
        print(f"tests failed (round {i + 1}), asking agent to fix")
        messages = continue_agent(
            messages,
            "实现已完成，但验证命令执行失败。请定位根因并修复，不要扩大改动范围，"
            "不要修改受保护路径。\n\n$ "
            + test_cmd
            + "\n"
            + output,
            max_rounds=30,
        )
    return True, ""


def main():
    number = os.environ["ISSUE_NUMBER"]
    cfg = load_config()
    branch_prefix = cfg.get("branchPrefix", "auto/")
    max_dev_rounds = int(cfg.get("maxDevRounds", 60))
    max_fix_rounds = int(cfg.get("maxFixRounds", 2))
    test_cmd = (cfg.get("testCommand") or "").strip()

    issue = json.loads(gh("issue", "view", number, "--json", "title,comments"))
    plan = find_plan(issue)
    if not plan:
        gh(
            "issue",
            "comment",
            number,
            "--body",
            "未找到自动生成的方案评论。请先为本 Issue 添加 `proposal` 标签生成方案，"
            "人工审核通过后再添加 `approved` 标签进入开发。",
        )
        print("no plan found")
        return

    title = issue["title"]
    branch = f"{branch_prefix}issue-{number}-{slugify(title)}"[:80]

    sh(["git", "config", "user.name", os.environ.get("GIT_BOT_NAME", "auto-dev-bot")])
    sh(["git", "config", "user.email", os.environ.get("GIT_BOT_EMAIL", "auto-dev-bot@users.noreply.github.com")])
    sh(["git", "fetch", "origin"])
    if sh(["git", "ls-remote", "--heads", "origin", branch]).strip():
        sh(["git", "checkout", "-B", branch, f"origin/{branch}"])
        print(f"reuse existing branch {branch}")
    else:
        sh(["git", "checkout", "-B", branch, "origin/main"])
        print(f"create new branch {branch}")

    user = (
        "# 开发方案（已人工审核，必须全部实现）\n\n"
        + plan
        + "\n\n# 仓库结构\n```\n"
        + repo_tree()
        + "\n```\n\n请开始：先浏览仓库确认现状，然后逐一实现任务清单中的全部任务。"
    )
    messages = run_agent(DEVELOPER_SYSTEM, user, max_rounds=max_dev_rounds)
    summary = last_assistant_text(messages)[:3000]

    test_note = ""
    if test_cmd:
        ok, output = run_tests(test_cmd, max_fix_rounds, messages)
        if not ok:
            test_note = f"\n\n⚠️ 验证命令仍失败（已达最大修复轮数）：\n```\n$ {test_cmd}\n{output}\n```"
        summary = last_assistant_text(messages)[:3000]

    sh(["git", "add", "-A"])
    if not sh(["git", "status", "--porcelain"]).strip():
        gh("issue", "comment", number, "--body", "开发完成，但没有检测到文件变更。" + test_note)
        print("no changes")
        return
    sh(["git", "commit", "-m", f"auto: implement issue #{number}"])
    sh(["git", "push", "-u", "origin", branch])

    tasks = "\n".join(l for l in plan.splitlines() if l.strip().startswith("- ["))
    body = (
        f"自动开发，对应 Issue #{number}\n\nCloses #{number}\n\n"
        f"## 实现摘要\n{summary}{test_note}\n\n"
        f"## 任务清单\n{tasks or '（见 Issue 中的方案）'}\n\n"
        "---\n🤖 由 auto-dev 工作流自动生成"
    )
    prs = json.loads(gh("pr", "list", "--head", branch, "--json", "number,url"))
    if prs:
        pr_no, pr_url = prs[0]["number"], prs[0]["url"]
        gh("pr", "comment", str(pr_no), "--body-file", "-", input_text=f"已更新实现。\n\n## 最新摘要\n{summary}{test_note}")
        print(f"updated PR {pr_url}")
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(body)
            body_file = f.name
        out = gh("pr", "create", "--title", f"auto: {title} (#{number})", "--body-file", body_file)
        pr_url = out.strip()
        print(f"created PR {pr_url}")

    gh("issue", "comment", number, "--body-file", "-", input_text=f"开发完成，PR：{pr_url}\n\n## 摘要\n{summary}{test_note}")


if __name__ == "__main__":
    main()
