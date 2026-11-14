"""session-start: the paste that opens a web-chat fallback session.

``veraxi-ymmp session-start`` prints one markdown document — slim
rules, live git state, open TODOs, and the session's command
cheatsheet — ready to paste as the first message of a web chat so the
model starts oriented instead of guessing (WP7). The full procedure
lives in docs/WEB_CHAT_RUNBOOK.md; this is its bootstrap.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Sequence

from veraxi_ymmp.app import pack_apply as pa

TODO_LIMIT = 20
DIRTY_LIMIT = 20
COMMIT_COUNT = 5


def _git_lines(root: Path, *args: str) -> List[str]:
    """Git output lines, or [] when git is unavailable/fails."""
    try:
        proc = pa._git(root, *args)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _rules_text(root: Path) -> str:
    """AGENTS_WEB.md when present, else AGENTS.md, else a stub."""
    for name in ("AGENTS_WEB.md", "AGENTS.md"):
        path = root / name
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return "(no AGENTS_WEB.md / AGENTS.md found at the repo root)"


def _collect_todos(root: Path) -> List[str]:
    """TODO/FIXME lines from tracked .py/.md files, via git grep."""
    lines = _git_lines(
        root, "grep", "-n", "-E", "TODO|FIXME", "--", "*.py", "*.md"
    )
    return lines[:TODO_LIMIT] + (
        [f"... and {len(lines) - TODO_LIMIT} more"]
        if len(lines) > TODO_LIMIT
        else []
    )


def build_session_start(root: Path) -> str:
    """Assemble the session-start document for the repo at root."""
    branch_lines = _git_lines(root, "branch", "--show-current")
    branch = branch_lines[0] if branch_lines else "(unknown)"
    commits = _git_lines(
        root, "log", "--oneline", f"-{COMMIT_COUNT}"
    ) or ["(no commits yet)"]
    dirty = _git_lines(root, "status", "--porcelain")
    if dirty:
        tree = [f"{len(dirty)} uncommitted change(s):"]
        tree += [f"- `{line}`" for line in dirty[:DIRTY_LIMIT]]
        if len(dirty) > DIRTY_LIMIT:
            tree.append(f"- ... and {len(dirty) - DIRTY_LIMIT} more")
    else:
        tree = ["clean"]
    todos = _collect_todos(root) or ["(none found in tracked .py/.md)"]

    parts = [
        "# veraxi-ymmp — web-chat session start",
        "",
        "You are helping develop the veraxi-ymmp repository from a "
        "web chat. The human runs the commands below locally and "
        "pastes results back. Follow the rules exactly; when a tool "
        "prints a re-prompt block, answer it precisely instead of "
        "improvising.",
        "",
        "## Rules",
        "",
        _rules_text(root),
        "",
        "## Repository state",
        "",
        f"- Branch: `{branch}`",
        "- Recent commits:",
    ]
    parts += [f"  - {line}" for line in commits]
    parts.append("- Working tree:")
    parts += [f"  {line}" for line in tree]
    parts += ["", "## Open TODOs", ""]
    parts += [f"- {line}" for line in todos]
    parts += [
        "",
        "## Session commands (human runs these locally)",
        "",
        "- Pack a task: `veraxi-ymmp pack --task \"<task>\" "
        "--files <paths> [-o bundle.md]` "
        "(`--mode edit` for files over ~400 lines)",
        "- Apply a full-file reply: `veraxi-ymmp apply reply.md "
        "--manifest bundle.md.manifest.json`",
        "- Apply an edit reply: `veraxi-ymmp apply-edit reply.md`",
        "- NotebookLM -> Web-chat script handoff: `veraxi-ymmp ingest-script "
        "projects/<slug>/evidence.md --provider manual`",
        "- (Optional) Ingest web-generated clips: `veraxi-ymmp ingest-clips "
        "<folder> --from-manifest clip-manifest.json`",
        "- Full procedure: `docs/WEB_CHAT_RUNBOOK.md`",
        "",
        "## How to reply",
        "",
        "- Full mode: return COMPLETE file contents in the bundle's "
        "reply format, ending with the END OF REPLY marker. Never "
        "elide (\"rest unchanged\"), never summarize code.",
        "- Edit mode: return only SEARCH/REPLACE blocks whose SEARCH "
        "text quotes the current file verbatim and matches exactly "
        "once.",
        "- Scripts: a single JSON object "
        "`{\"script\": [...], \"broll_manifest\": [...]}`.",
    ]
    return "\n".join(parts) + "\n"


def cmd_session_start(argv: Sequence[str]) -> int:
    """Print the session-start document for the current repo."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp session-start",
        description="Print the web-chat session-start paste.",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Write to this file instead of stdout.",
    )
    args = parser.parse_args(list(argv))
    root = pa._repo_root()
    text = build_session_start(root)
    if args.output:
        out = Path(args.output)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out} ({len(text)} chars)")
    else:
        print(text, end="")
    return 0
