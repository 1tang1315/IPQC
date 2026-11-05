"""auto-dev 流水线共享模块：LLM 客户端 + 受限仓库文件工具 + agent 工具循环。

所有脚本只依赖 Python 标准库，便于在 GitHub Actions 裸 runner 上直接运行。
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()

PLAN_MARKER = "<!-- auto-dev-plan -->"

MAX_TOOL_OUTPUT = 30000
MAX_READ_FILE = 200_000
MAX_WRITE_FILE = 100_000

_config_cache = None


# ---------------------------------------------------------------- config


def load_config():
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads(
                (ROOT / ".github" / "auto-dev.json").read_text(encoding="utf-8")
            )
        except Exception:
            _config_cache = {}
    return _config_cache


def llm_settings():
    cfg = load_config()
    return {
        "base_url": os.environ.get("LLM_BASE_URL")
        or cfg.get("baseUrl")
        or "https://api.kimi.com/coding/v1",
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL") or cfg.get("defaultModel") or "kimi-for-coding",
    }


class LLMError(Exception):
    pass


# ---------------------------------------------------------------- llm client


def chat(messages, tools=None, model=None, max_tokens=16000, temperature=0.2, retries=4):
    """调用 OpenAI 兼容的 chat/completions 接口，返回 message 字典。"""
    s = llm_settings()
    if not s["api_key"]:
        raise LLMError("LLM_API_KEY is not set")
    body = {
        "model": model or s["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
    url = s["base_url"].rstrip("/") + "/chat/completions"
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + s["api_key"],
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:800]
            last_err = LLMError(f"LLM HTTP {e.code}: {detail}")
            if e.code in (408, 409, 425, 429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = LLMError(f"LLM network error: {e}")
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise last_err
    raise last_err


# ---------------------------------------------------------------- file tools


def safe_path(rel):
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise ValueError(f"unsafe path: {rel!r}")
    p = (ROOT / rel).resolve()
    if p != ROOT and not str(p).startswith(str(ROOT) + os.sep):
        raise ValueError(f"path escapes repo: {rel!r}")
    return p


def is_protected(rel):
    norm = rel.replace(os.sep, "/")
    for p in load_config().get("protectedPaths", []):
        p = p.strip("/")
        if norm == p or norm.startswith(p + "/"):
            return True
    return False


def _list_files(args):
    rel = args.get("path") or "."
    max_entries = int(args.get("max_entries") or 200)
    p = safe_path(rel)
    if not p.is_dir():
        return f"ERROR: not a directory: {rel}"
    out = []
    children = sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower()))
    for child in children[:max_entries]:
        out.append(child.name + ("/" if child.is_dir() else ""))
    if len(children) > max_entries:
        out.append(f"... ({max_entries}/{len(children)} shown, truncated)")
    return "\n".join(out) or "(empty)"


def _read_file(args):
    p = safe_path(args["path"])
    if not p.is_file():
        return f"ERROR: file not found: {args['path']}"
    if p.stat().st_size > MAX_READ_FILE:
        return f"ERROR: file too large (>{MAX_READ_FILE} bytes): {args['path']}"
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "ERROR: not a UTF-8 text file"


def _write_file(args):
    rel = args["path"]
    if is_protected(rel):
        return f"ERROR: path is protected by policy: {rel}"
    p = safe_path(rel)
    content = args.get("content")
    if content is None:
        return "ERROR: missing content"
    if len(content) > MAX_WRITE_FILE:
        return f"ERROR: content too large (max {MAX_WRITE_FILE} chars)"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"written: {rel} ({len(content)} chars)"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出仓库内某个目录的文件（相对路径，默认根目录）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对目录路径，如 src 或 ."},
                    "max_entries": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取仓库内一个文本文件（相对路径）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "新建或覆盖仓库内一个文本文件（相对路径）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

_TOOL_IMPLS = {"list_files": _list_files, "read_file": _read_file, "write_file": _write_file}


def run_tool(name, args):
    impl = _TOOL_IMPLS.get(name)
    if impl is None:
        return f"ERROR: unknown tool: {name}"
    try:
        return impl(args or {})
    except (ValueError, KeyError, OSError) as e:
        return f"ERROR: {e}"


def _run_tool_loop(messages, max_rounds, model=None):
    for _ in range(max_rounds):
        msg = chat(messages, tools=TOOL_SCHEMAS, model=model)
        clean = {k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")}
        messages.append(clean)
        tool_calls = clean.get("tool_calls") or []
        if not tool_calls:
            return messages
        for tc in tool_calls:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(fn.get("name", ""), args)
            if len(result) > MAX_TOOL_OUTPUT:
                result = result[:MAX_TOOL_OUTPUT] + "\n...[truncated]"
            messages.append(
                {"role": "tool", "tool_call_id": tc.get("id", ""), "content": result}
            )
    raise LLMError(f"agent exceeded max rounds ({max_rounds})")


def run_agent(system_prompt, user_prompt, max_rounds=50, model=None):
    """从 system+user 起步，带工具循环跑 agent，返回完整 messages 列表。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _run_tool_loop(messages, max_rounds, model=model)


def continue_agent(messages, user_message, max_rounds=30, model=None):
    """在既有对话上追加一条 user 消息继续跑工具循环。"""
    messages.append({"role": "user", "content": user_message})
    return _run_tool_loop(messages, max_rounds, model=model)


def last_assistant_text(messages):
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            return m["content"].strip()
    return ""


# ---------------------------------------------------------------- helpers


def gh(*args, check=True, input_text=None):
    env = dict(os.environ)
    env.setdefault("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    r = subprocess.run(
        ["gh", *[str(a) for a in args]],
        capture_output=True,
        text=True,
        env=env,
        input=input_text,
        timeout=300,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(str(a) for a in args)} failed: {r.stderr.strip()[:800]}")
    return r.stdout


_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", "target", ".idea", ".vscode", "out", "coverage", ".pytest_cache",
}


def repo_tree(max_entries=300, max_depth=2):
    """生成仓库目录树快照（有限深度/条目），用于 LLM 上下文。"""
    lines = []

    def walk(d, prefix, depth):
        if depth > max_depth or len(lines) >= max_entries:
            return
        try:
            children = sorted(
                (c for c in d.iterdir() if c.name not in _SKIP_DIRS and not c.name.startswith(".")),
                key=lambda c: (c.is_file(), c.name.lower()),
            )
        except OSError:
            return
        for c in children:
            if len(lines) >= max_entries:
                lines.append("...")
                return
            lines.append(prefix + c.name + ("/" if c.is_dir() else ""))
            if c.is_dir():
                walk(c, prefix + "  ", depth + 1)

    walk(ROOT, "", 0)
    return "\n".join(lines)


def ensure_label(name, color="BFD4F2"):
    gh("label", "create", name, "--color", color, "--force")


def slugify(text, max_len=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "task"


def extract_json(text):
    """从模型输出中提取第一个 JSON 对象，失败返回 None。"""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
