"""pack / apply: the coding-agent fallback for web-chat models.

When a web chat (e.g. Gemini) has to stand in for a local coding agent,
``veraxi-ymmp pack`` emits ONE markdown bundle — the task, the AGENTS.md
rules, the named files, and the failing test output — with a strict
reply format. ``veraxi-ymmp apply`` parses the reply's file blocks
(full-file replacement only), applies them on a fresh git branch, and
runs ruff / mypy / the targeted pytest, printing any failures as the
next paste-back re-prompt block, in the same style as the script loop.

Safety invariants:
- pack fails loudly when the bundle exceeds the character budget; it
  never truncates silently.
- apply validates the whole reply before touching anything: a malformed
  or incomplete (truncated) reply is rejected with zero files modified,
  and the model is asked for a continuation instead.
- apply refuses paths outside the repo, anything under .git, and test
  files unless --allow-tests is given.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

DEFAULT_BUDGET = 60_000
END_MARKER = "===END OF REPLY==="
CONTINUATION_MARKER = "===CONTINUATION REQUIRED==="

_FILE_HEADER = re.compile(r"^#{2,3}\s+File:\s*`([^`]+)`\s*$")
_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_+.-]*\s*$")

OutputFn = Callable[[str], None]
CheckRunner = Callable[
    [List[str], Optional[str], Path], List[Tuple[str, str]]
]


@dataclass
class ParsedReply:
    """Result of parsing a web-chat reply into full-file blocks."""

    blocks: List[Tuple[str, str]] = field(default_factory=list)
    complete: bool = False
    problem: str = ""


def parse_reply(text: str) -> ParsedReply:
    """Parse '### File: `path`' + fenced-block pairs from a reply.

    A reply is complete only when every fence is closed and the
    END_MARKER line is present without a CONTINUATION_MARKER — anything
    else is treated as truncated output from the web chat.
    """
    lines = text.splitlines()
    blocks: List[Tuple[str, str]] = []
    problem = ""
    saw_end = False
    saw_continuation = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == END_MARKER:
            saw_end = True
        elif stripped == CONTINUATION_MARKER:
            saw_continuation = True
        header = _FILE_HEADER.match(lines[i])
        if header:
            rel_path = header.group(1)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines) or not _FENCE_OPEN.match(lines[j]):
                problem = f"file block for {rel_path!r} is not followed by a code fence"
                break
            content_lines: List[str] = []
            k = j + 1
            closed = False
            while k < len(lines):
                if lines[k].strip() == "```":
                    closed = True
                    break
                content_lines.append(lines[k])
                k += 1
            if not closed:
                problem = f"file block for {rel_path!r} is truncated (unclosed fence)"
                break
            content = "\n".join(content_lines)
            if content_lines:
                content += "\n"
            blocks.append((rel_path, content))
            i = k + 1
            continue
        i += 1
    if not problem:
        if not blocks:
            problem = "no file blocks found in reply"
        elif saw_continuation:
            problem = f"reply declares {CONTINUATION_MARKER}"
        elif not saw_end:
            problem = f"missing {END_MARKER} marker (reply may be truncated)"
    return ParsedReply(blocks=blocks, complete=not problem, problem=problem)


def validate_target_paths(
    blocks: List[Tuple[str, str]], root: Path, allow_tests: bool
) -> List[str]:
    """Return safety errors for the reply's target paths (empty = safe)."""
    errors: List[str] = []
    root_resolved = root.resolve()
    for rel_path, _content in blocks:
        candidate = Path(rel_path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root_resolved / candidate).resolve()
        )
        if resolved != root_resolved and root_resolved not in resolved.parents:
            errors.append(f"{rel_path}: path escapes the repository root")
            continue
        parts = resolved.relative_to(root_resolved).parts
        if ".git" in parts:
            errors.append(f"{rel_path}: refusing to modify .git internals")
        elif parts and parts[0] == "tests" and not allow_tests:
            errors.append(
                f"{rel_path}: refusing to modify tests without --allow-tests"
            )
    return errors


def format_continuation_request(parsed: ParsedReply) -> str:
    """Re-prompt block asking the model to resend/continue an incomplete reply."""
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
        "Your reply was NOT applied because it appears incomplete:",
        f"  - [INCOMPLETE] {parsed.problem}",
        "Please resend the COMPLETE reply with every file block, ending with a "
        f"line containing only {END_MARKER}.",
        "If the full reply does not fit in one message, end with a line "
        f"containing only {CONTINUATION_MARKER} after the last complete file "
        "block, and continue in the next message.",
        "==========================================================================",
    ]
    return "\n".join(lines)


def format_check_reprompt(branch: str, failures: List[Tuple[str, str]]) -> str:
    """Re-prompt block with check failures, ready to paste back to the model."""
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
        f"Your changes were applied on branch {branch}, but checks failed:",
    ]
    for kind, output in failures:
        lines.append(f"  - [{kind}] {output}")
    lines.append(
        "Please fix these failures and return the complete corrected file "
        f"blocks, ending with a line containing only {END_MARKER}."
    )
    lines.append("==========================================================================")
    return "\n".join(lines)


def run_check_commands(
    changed: List[str], test_path: Optional[str], root: Path
) -> List[Tuple[str, str]]:
    """Run ruff, mypy and the targeted pytest; return (kind, output) failures."""
    failures: List[Tuple[str, str]] = []
    py_files = [p for p in changed if p.endswith(".py")]
    commands: List[Tuple[str, List[str]]] = []
    if py_files:
        commands.append(("RUFF", [sys.executable, "-m", "ruff", "check", *py_files]))
        commands.append(("MYPY", [sys.executable, "-m", "mypy", *py_files]))
    if test_path:
        commands.append(
            ("PYTEST", [sys.executable, "-m", "pytest", test_path, "-q",
                        "-p", "no:cacheprovider"])
        )
    for kind, cmd in commands:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, timeout=900
        )
        if proc.returncode != 0:
            output = (proc.stdout + proc.stderr).strip()
            failures.append((kind, output[-4000:]))
    return failures


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60
    )


def apply_reply(
    reply_text: str,
    root: Path,
    allow_tests: bool = False,
    test_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    check_runner: CheckRunner = run_check_commands,
    output_fn: OutputFn = print,
) -> int:
    """Apply a parsed reply on a new git branch and run the checks.

    Returns 0 when the reply applied cleanly and all checks pass, 1
    otherwise. A rejected reply (incomplete, malformed, unsafe paths)
    modifies no files and creates no branch.
    """
    parsed = parse_reply(reply_text)
    if not parsed.blocks:
        output_fn(f"Error: reply rejected — {parsed.problem}. No files modified.")
        return 1
    if not parsed.complete:
        output_fn(format_continuation_request(parsed))
        return 1
    path_errors = validate_target_paths(parsed.blocks, root, allow_tests)
    if path_errors:
        for error in path_errors:
            output_fn(f"Error: reply rejected — {error}. No files modified.")
        return 1

    branch = branch_name or f"agent-apply-{datetime.now():%Y%m%d-%H%M%S}"
    proc = _git(root, "checkout", "-b", branch)
    if proc.returncode != 0:
        output_fn(f"Error: could not create branch {branch}: {proc.stderr.strip()}")
        return 1

    changed: List[str] = []
    for rel_path, content in parsed.blocks:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changed.append(rel_path)
    output_fn(f"Applied {len(changed)} file(s) on branch {branch}:")
    for rel_path in changed:
        output_fn(f"  - {rel_path}")

    failures = check_runner(changed, test_path, root)
    if failures:
        output_fn(format_check_reprompt(branch, failures))
        return 1
    output_fn("All checks passed (ruff, mypy, targeted pytest).")
    return 0


def _run_failing_test(test_path: str, root: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider"],
        cwd=root, capture_output=True, text=True, timeout=900,
    )
    return (proc.stdout + proc.stderr).strip()


def build_pack_bundle(
    task: str,
    file_contents: List[Tuple[str, str]],
    agents_md: str,
    test_path: Optional[str] = None,
    test_output: str = "",
) -> str:
    """Assemble the single markdown bundle for a web-chat coding task."""
    parts: List[str] = ["# Coding Task Bundle", "", "## Task", task, ""]
    parts += ["## Rules (AGENTS.md)", agents_md.strip(), ""]
    parts.append("## Files")
    for rel_path, content in file_contents:
        lang = "python" if rel_path.endswith(".py") else "text"
        parts += [f"### File: `{rel_path}`", f"```{lang}", content.rstrip("\n"),
                  "```", ""]
    if test_path:
        parts += ["## Failing Tests", f"$ pytest {test_path} -q", "```text",
                  test_output, "```", ""]
    parts += [
        "## Reply Format (strict — follow exactly)",
        "Reply with ONLY file blocks, one per file you change, in this format:",
        "",
        "### File: `relative/path/from/repo/root.py`",
        "followed immediately by a fenced code block containing the COMPLETE "
        "new content of that file (full-file replacement — no diffs, no "
        "elision, no 'rest unchanged' placeholders).",
        "",
        "End the reply with a line containing only:",
        END_MARKER,
        "If the complete reply does not fit in one message, end instead "
        "with a line containing only:",
        CONTINUATION_MARKER,
        "after the last complete file block. A truncated or marker-less "
        "reply is rejected without applying anything.",
        "",
    ]
    return "\n".join(parts)


def _repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path.cwd()


def cmd_pack(argv: Sequence[str]) -> None:
    """Handle 'veraxi-ymmp pack'."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp pack",
        description="Emit one markdown bundle for a web-chat coding agent.",
    )
    parser.add_argument("--task", required=True, help="Task description text")
    parser.add_argument("--files", nargs="+", required=True,
                        help="Repo-relative files to include in the bundle")
    parser.add_argument("--test", default=None,
                        help="Targeted pytest file whose current output is included")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                        help=f"Max bundle characters (default {DEFAULT_BUDGET})")
    parser.add_argument("-o", "--output", default=None,
                        help="Write the bundle to this file (default: stdout)")
    args = parser.parse_args(list(argv))

    root = _repo_root()
    file_contents: List[Tuple[str, str]] = []
    for rel in args.files:
        path = root / rel
        if not path.is_file():
            sys.stderr.write(f"Error: file not found in repo: {rel}\n")
            sys.exit(2)
        file_contents.append((rel, path.read_text(encoding="utf-8")))
    agents_path = root / "AGENTS.md"
    agents_md = (
        agents_path.read_text(encoding="utf-8")
        if agents_path.is_file()
        else "(no AGENTS.md found at repo root)"
    )
    test_output = _run_failing_test(args.test, root) if args.test else ""
    bundle = build_pack_bundle(
        args.task, file_contents, agents_md,
        test_path=args.test, test_output=test_output,
    )
    if len(bundle) > args.budget:
        sys.stderr.write(
            f"Error: pack bundle is {len(bundle)} characters, over the "
            f"{args.budget}-character budget. Split the task or name fewer "
            "files; refusing to truncate silently.\n"
        )
        sys.exit(2)
    if args.output:
        Path(args.output).write_text(bundle, encoding="utf-8")
        print(f"Wrote pack bundle ({len(bundle)} chars) to {args.output}")
    else:
        print(bundle)


def cmd_apply(argv: Sequence[str]) -> None:
    """Handle 'veraxi-ymmp apply'."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp apply",
        description="Apply a web-chat reply's file blocks on a new git branch.",
    )
    parser.add_argument("reply", help="Path to the reply markdown file")
    parser.add_argument("--allow-tests", action="store_true",
                        help="Allow the reply to modify files under tests/")
    parser.add_argument("--test", default=None,
                        help="Targeted pytest file to run after applying")
    parser.add_argument("--branch", default=None,
                        help="Branch name to create (default: agent-apply-<timestamp>)")
    args = parser.parse_args(list(argv))

    reply_path = Path(args.reply)
    if not reply_path.is_file():
        sys.stderr.write(f"Error: reply file not found: {reply_path}\n")
        sys.exit(2)
    code = apply_reply(
        reply_path.read_text(encoding="utf-8"),
        _repo_root(),
        allow_tests=args.allow_tests,
        test_path=args.test,
        branch_name=args.branch,
    )
    sys.exit(code)
