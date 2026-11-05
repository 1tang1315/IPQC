"""auto-review：对 PR 进行 AI 代码评审，提交 GitHub PR Review
（Approve 或 Request changes）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai import chat, extract_json, gh  # noqa: E402

REVIEW_SYSTEM = """你是严格的资深代码评审专家。只依据给出的 PR 标题、描述与 diff 进行评审。

输出必须是 JSON（不要输出其他任何内容），格式：
{"verdict":"approve 或 request_changes","summary":"整体评价（几句话）","findings":[{"severity":"critical|major|minor","file":"文件路径","detail":"问题描述与修改建议"}]}

规则：
- 存在 critical 或 major 问题 → verdict 为 request_changes；否则 approve。
- 关注：功能正确性、安全漏洞（注入、密钥泄漏等）、明显性能问题、与仓库风格的一致性。
- 不要报风格洁癖、格式偏好类问题；不要臆测 diff 被截断部分的内容。
- findings 为空时输出空数组，不要硬凑问题。
"""

DIFF_MAX = 120000


def review(pr_number, repo):
    pr = json.loads(
        gh("pr", "view", pr_number, "--json", "title,body,isDraft,headRefName,url")
    )
    if pr["isDraft"]:
        print(f"PR #{pr_number} 是草稿，跳过评审")
        return
    diff = gh("pr", "diff", pr_number)
    if len(diff) > DIFF_MAX:
        half = DIFF_MAX // 2
        diff = (
            diff[:half]
            + f"\n\n... [diff 过大已截断：共 {len(diff)} 字符] ...\n\n"
            + diff[-half:]
        )
    user = (
        f"# PR #{pr_number}: {pr['title']}\n\n{pr['body'][:3000]}\n\n"
        f"# Diff\n```diff\n{diff}\n```\n\n请评审并输出 JSON。"
    )
    msg = chat(
        [{"role": "system", "content": REVIEW_SYSTEM}, {"role": "user", "content": user}],
        max_tokens=8000,
    )
    raw = msg.get("content") or ""
    result = extract_json(raw)
    if result is None:
        body = (
            "⚠️ AI 评审结果解析失败，以下为其原始输出，请人工确认：\n\n```\n"
            + raw[:10000]
            + "\n```"
        )
        event = "COMMENT"
    else:
        verdict = str(result.get("verdict", "")).lower()
        summary = result.get("summary") or "（无）"
        findings = result.get("findings") or []
        lines = []
        for f in findings:
            sev = f.get("severity", "?")
            path = f.get("file", "")
            detail = (f.get("detail") or "").strip()
            lines.append(f"- **{sev}** `{path}` — {detail}" if path else f"- **{sev}** {detail}")
        if verdict == "approve":
            event = "APPROVE"
            body = "✅ AI 评审通过\n\n" + summary
        else:
            event = "REQUEST_CHANGES"
            body = "❌ AI 评审未通过，请修复以下问题\n\n**整体评价**\n" + summary
        if lines:
            body += "\n\n**问题清单**\n" + "\n".join(lines)
        body += "\n\n---\n🤖 由 auto-dev 工作流自动评审"
    payload = json.dumps({"event": event, "body": body[:60000]})
    gh("api", f"repos/{repo}/pulls/{pr_number}/reviews", "--input", "-", input_text=payload)
    print(f"PR #{pr_number}: review submitted ({event})")


def main():
    review(os.environ["PR_NUMBER"], os.environ["GITHUB_REPOSITORY"])


if __name__ == "__main__":
    main()
