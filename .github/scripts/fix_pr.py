"""auto-fix：PR 被 AI 评审打回（Request changes）时，按评审意见自动修复并推送。
带轮数上限保险，超限后留言转人工。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai import gh, last_assistant_text, load_config, run_agent  # noqa: E402

BOT_LOGIN = "github-actions[bot]"

FIX_SYSTEM = """你是资深开发工程师，在 CI 环境中根据代码评审意见修复 PR。

工作要求：
1. 仔细阅读评审意见中的每个 finding，逐一修复（severity 为 critical/major 的必须修复，minor 的尽量修复）。
2. 修复要最小化改动，保持仓库现有代码风格，不要借机重构无关代码。
3. 禁止臆造 API，不确定时先 read_file 阅读相关代码。
4. 不要修改 .github/ 下的工作流与脚本（受保护路径）。
5. 完成后用最后一条消息输出修复摘要：每条意见如何处理、修改了哪些文件。
"""


def sh(args, check=True, timeout=900):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
        )
    return r


def main():
    number = os.environ["PR_NUMBER"]
    cfg = load_config()
    branch_prefix = cfg.get("branchPrefix", "auto/")
    max_rounds = int(cfg.get("maxReviewRounds", 3))

    pr = json.loads(
        gh("pr", "view", number, "--json", "headRefName,reviews,title")
    )
    head = pr["headRefName"]
    if not head.startswith(branch_prefix):
        print(f"skip non-auto branch: {head}")
        return

    bot_reviews = [
        r for r in pr.get("reviews", []) if (r.get("author") or {}).get("login") == BOT_LOGIN
    ]
    requested = [r for r in bot_reviews if r.get("state") == "CHANGES_REQUESTED"]
    if len(requested) >= max_rounds:
        gh(
            "pr",
            "comment",
            number,
            "--body",
            f"已达最大自动修复轮数（{max_rounds}），请人工介入处理剩余评审意见。",
        )
        print("max review rounds reached, hand over to human")
        return
    if not requested:
        print("no bot CHANGES_REQUESTED review found")
        return
    review_body = requested[-1].get("body") or ""

    diff = gh("pr", "diff", number)
    if len(diff) > 120000:
        diff = diff[:60000] + "\n...[diff truncated]...\n" + diff[-60000:]

    sh(["git", "config", "user.name", os.environ.get("GIT_BOT_NAME", "auto-dev-bot")])
    sh(["git", "config", "user.email", os.environ.get("GIT_BOT_EMAIL", "auto-dev-bot@users.noreply.github.com")])
    sh(["git", "fetch", "origin"])
    sh(["git", "checkout", "-B", head, f"origin/{head}"])

    user = (
        f"# PR #{number}: {pr['title']}\n\n# 评审意见\n{review_body}\n\n"
        f"# 当前 diff\n```diff\n{diff}\n```\n\n"
        "请基于当前代码逐一修复上述评审意见。"
    )
    messages = run_agent(FIX_SYSTEM, user, max_rounds=int(cfg.get("maxDevRounds", 60)))
    summary = last_assistant_text(messages)[:3000]

    sh(["git", "add", "-A"])
    if not sh(["git", "status", "--porcelain"]).strip():
        gh("pr", "comment", number, "--body", "评审意见已处理，未检测到需要修改的内容。")
        print("no changes")
        return
    sh(["git", "commit", "-m", f"auto: fix review comments for PR #{number}"])
    sh(["git", "push", "origin", head])
    gh("pr", "comment", number, "--body-file", "-", input_text=f"已按评审意见修复并推送。\n\n## 修复摘要\n{summary}")
    print(f"pushed fixes to {head}")


if __name__ == "__main__":
    main()
