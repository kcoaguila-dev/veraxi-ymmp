"""pack / apply: the coding-agent fallback for web-chat models.

When a web chat (e.g. Gemini) has to stand in for a local coding agent,
``veraxi-ymmp pack`` emits ONE markdown bundle — the task, the rules
(AGENTS_WEB.md by default, the slim web-chat distillation of
AGENTS.md; --rules PATH overrides), the named files, and the failing
test output — with a strict reply format. ``veraxi-ymmp apply`` parses the reply's file blocks
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
- WP2 guards, all checked before any branch or file is touched:
  `pack -o` writes a manifest sidecar (path, sha256, line count per
  file); `apply --manifest` rejects targets outside the manifest
  (unless --allow-new) and targets whose current content has drifted
  from the packed hash (unless --force-stale); an elision detector
  rejects lazy replies ("rest of the file", "unchanged", bare "...")
  in lines that are new relative to the old file (unless
  --allow-elision); a shrink guard
  rejects a file that loses over 40% of its lines or becomes empty
  (unless --allow-shrink).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

DEFAULT_BUDGET = 60_000
END_MARKER = "===END OF REPLY==="
CONTINUATION_MARKER = "===CONTINUATION REQUIRED==="

_FILE_HEADER = re.compile(r"^#{2,3}\s+File:\s*`([^`]+)`\s*$")
# A fence line is a run of >= 3 backticks, an optional language tag, and
# nothing else. Group 1 is the backtick run, group 2 the language tag.
_FENCE_LINE = re.compile(r"^(`{3,})([A-Za-z0-9_+.-]*)\s*$")
_FENCE_OPEN = _FENCE_LINE
_BACKTICK_RUN = re.compile(r"`+")


def _fence_for_content(content: str) -> str:
    """Return a fence longer than the longest backtick run in *content*.

    Minimum 4 backticks, matching the Reply Format instructions.
    Wrapping a file this way means an inner fence in the file can
    never be mistaken for the block's closing fence.
    """
    longest = 0
    for match in _BACKTICK_RUN.finditer(content):
        longest = max(longest, len(match.group(0)))
    return "`" * max(4, longest + 1)

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


def _read_block(
    lines: List[str], start: int, open_run: int
) -> Tuple[List[str], int]:
    """Read one fenced block's content from *lines* starting at *start*.

    *open_run* is the opening fence's backtick count. Returns the
    content lines and the index of the closing fence line, or -1 when
    the block is unclosed. See parse_reply for the fence rules.
    """
    stack: List[int] = [open_run]
    content_lines: List[str] = []
    k = start
    while k < len(lines):
        fence = _FENCE_LINE.match(lines[k].strip())
        if fence is None:
            content_lines.append(lines[k])
            k += 1
            continue
        run = len(fence.group(1))
        if fence.group(2):
            # A tagged fence opens a nested level only when it could
            # interact with the block's own fence. A shorter tagged
            # fence (e.g. a lone ```python line inside a 4-backtick
            # block) can never close the block, so it is plain content;
            # pushing it would let the real closer pop the wrong level
            # and falsely report the block as unclosed.
            if run >= stack[0]:
                stack.append(run)
            content_lines.append(lines[k])
            k += 1
            continue
        if len(stack) > 1:
            if run >= stack[-1]:
                stack.pop()
            content_lines.append(lines[k])
            k += 1
            continue
        if run >= stack[0]:
            return content_lines, k
        # A shorter bare fence is ordinary content (e.g. the closing
        # fence of an inner block wrapped in a longer outer fence).
        content_lines.append(lines[k])
        k += 1
    return content_lines, -1


def _strip_outer_wrapper(
    lines: List[str],
) -> Tuple[List[str], Optional[str]]:
    """Remove a whole-reply wrapper fence, strictly at the envelope.

    Web chats often wrap an entire reply in one outer fence. Unwrap
    only when the first non-empty line is a fence and the last
    non-empty line is a bare fence whose run is at least as long:
    then the pair is unambiguously an envelope, and removing it
    before parsing cannot be confused with any fence inside a file
    block. Returns (lines, None) on success or when there is no
    wrapper at all, and (lines, problem) when the reply opens with a
    fence but has no valid closing wrapper fence — that case must
    fail closed, because the opening fence means the reply *claims*
    to be wrapped, so a missing, tagged, or shorter closer is
    evidence of truncation, not a plain unwrapped reply.
    """
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    if start >= end:
        return lines, None
    first, last = start, end - 1
    open_match = _FENCE_LINE.match(lines[first].strip())
    if open_match is None:
        return lines, None
    close_match = _FENCE_LINE.match(lines[last].strip())
    if (
        first == last
        or close_match is None
        or close_match.group(2)
        or len(close_match.group(1)) < len(open_match.group(1))
    ):
        return lines, "unclosed wrapper code fence"
    return lines[first + 1:last], None


def parse_reply(text: str) -> ParsedReply:
    """Parse '### File: `path`' + fenced-block pairs from a reply.

    A reply is complete only when every fence is closed and the
    END_MARKER line is present without a CONTINUATION_MARKER — anything
    else is treated as truncated output from the web chat.

    Fence handling is length- and depth-aware so a file that itself
    contains code fences (every prompt template does) is not silently
    truncated at the first inner closing fence:

    - A block opened with n backticks closes only on a bare line of
      >= n backticks.
    - With same-length fences, a tagged inner fence opens a nested
      level and a bare fence closes the innermost level; the block
      closes when the depth returns to 0.
    - Safety net: a fence line outside any block after a block has
      closed is treated as evidence that an inner bare fence closed a
      block prematurely, and the whole reply is rejected.
    - A whole-reply wrapper fence is removed beforehand by
      _strip_outer_wrapper, strictly at the envelope, so no fence
      inside the reply can ever be mistaken for its closing fence.
      A reply that opens with a wrapper fence but has no valid
      closing wrapper fence is rejected outright (fail closed).
    """
    lines, wrapper_problem = _strip_outer_wrapper(text.splitlines())
    if wrapper_problem is not None:
        return ParsedReply(complete=False, problem=wrapper_problem)
    blocks: List[Tuple[str, str]] = []
    problem = ""
    saw_end = False
    saw_continuation = False
    last_closed_path = ""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == END_MARKER:
            saw_end = True
        elif stripped == CONTINUATION_MARKER:
            saw_continuation = True
        header = _FILE_HEADER.match(lines[i])
        if not header:
            if blocks and _FENCE_LINE.match(stripped):
                problem = (
                    f"stray code fence after block for {last_closed_path}; "
                    "nested fences likely broke the block"
                )
                break
            i += 1
            continue
        rel_path = header.group(1)
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        open_match = _FENCE_OPEN.match(lines[j].strip()) if j < len(lines) else None
        if open_match is None:
            problem = f"file block for {rel_path!r} is not followed by a code fence"
            break
        content_lines, k = _read_block(lines, j + 1, len(open_match.group(1)))
        if k < 0:
            problem = f"file block for {rel_path!r} is truncated (unclosed fence)"
            break
        content = "\n".join(content_lines)
        if content_lines:
            content += "\n"
        blocks.append((rel_path, content))
        last_closed_path = rel_path
        i = k + 1
        continue
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


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_manifest(
    file_contents: List[Tuple[str, str]], packed_at: Optional[str] = None
) -> Dict[str, Any]:
    """Manifest sidecar for a pack bundle: per-file hash + line count."""
    return {
        "packed_at": packed_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [
            {
                "path": rel_path,
                "sha256": _content_sha256(content),
                "line_count": len(content.splitlines()),
            }
            for rel_path, content in file_contents
        ],
    }


def load_manifest(path: Path) -> Dict[str, Any]:
    """Load and minimally validate a pack manifest sidecar."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError(f"manifest {path} has no 'files' list")
    return data


_ELISION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"rest of (the )?(file|code|function)",
        r"\bunchanged\b",
        r"same as before",
        r"remains the same",
        r"\bomitted\b",
    )
]
_ELLIPSIS_ONLY_LINE = re.compile(r"^(?:#|//|/\*|<!--)?\s*\.\.\.\s*(?:\*/|-->)?$")


def _elision_problems(
    rel_path: str, new_content: str, old_content: str
) -> List[str]:
    """Elision markers in lines that are new relative to the old file.

    Scanning only new lines keeps files that legitimately contain
    words like "unchanged" applicable, as long as the reply does not
    add new elision language of its own.
    """
    old_lines = set(old_content.splitlines())
    problems: List[str] = []
    for lineno, line in enumerate(new_content.splitlines(), start=1):
        if line in old_lines:
            continue
        if any(p.search(line) for p in _ELISION_PATTERNS) or (
            _ELLIPSIS_ONLY_LINE.match(line.strip())
        ):
            problems.append(
                f"{rel_path}:{lineno}: elision marker in new line: "
                f"{line.strip()!r}"
            )
    return problems


def validate_apply_guards(
    blocks: List[Tuple[str, str]],
    root: Path,
    manifest: Optional[Dict[str, Any]] = None,
    allow_new: Sequence[str] = (),
    force_stale: bool = False,
    allow_shrink: bool = False,
    allow_elision: bool = False,
) -> List[str]:
    """WP2 guards: manifest allowlist/stale base, elision, shrink.

    Returns problem strings (empty = all guards pass). Runs entirely
    against the current on-disk state, before any branch is created
    or any file is written.
    """
    problems: List[str] = []
    manifest_map: Dict[str, Dict[str, Any]] = {}
    if manifest is not None:
        manifest_map = {
            str(entry.get("path")): entry
            for entry in manifest.get("files", [])
            if isinstance(entry, dict)
        }
    allow_new_set = set(allow_new)
    for rel_path, new_content in blocks:
        target = root / rel_path
        old_content = (
            target.read_text(encoding="utf-8") if target.is_file() else ""
        )
        if manifest is not None:
            entry = manifest_map.get(rel_path)
            if entry is None:
                if rel_path not in allow_new_set:
                    problems.append(
                        f"{rel_path}: not in pack manifest "
                        f"(--allow-new {rel_path} permits a new file)"
                    )
            elif not force_stale:
                if not target.is_file() or (
                    _content_sha256(old_content) != entry.get("sha256")
                ):
                    problems.append(
                        f"{rel_path}: base drifted since pack; re-pack"
                    )
        if not allow_elision:
            problems.extend(
                _elision_problems(rel_path, new_content, old_content)
            )
        if not allow_shrink and target.is_file():
            old_count = len(old_content.splitlines())
            new_count = len(new_content.splitlines())
            if not new_content and old_content:
                problems.append(
                    f"{rel_path}: new content is empty "
                    "(--allow-shrink permits this)"
                )
            elif old_count >= 30 and new_count < 0.6 * old_count:
                problems.append(
                    f"{rel_path}: shrinks from {old_count} to {new_count} "
                    "lines (< 60% of the original; --allow-shrink "
                    "permits this)"
                )
    return problems


def format_guard_reprompt(problems: List[str]) -> str:
    """Re-prompt block for replies rejected by the WP2 apply guards."""
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
        "Your reply was NOT applied because it failed the apply guards:",
    ]
    for problem in problems:
        lines.append(f"  - [GUARD] {problem}")
    lines.append(
        "Please resend the COMPLETE content of every file — full-file "
        "replacement with no elision, no 'rest unchanged' placeholders, "
        f"and no shrinkage — ending with a line containing only {END_MARKER}."
    )
    lines.append("==========================================================================")
    return "\n".join(lines)


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


def _write_content_file(target: Path, content: str) -> None:
    """Write *content* respecting the repo's .gitattributes EOL rules.

    The repo sets `text=auto eol=lf` with CRLF only for .bat/.ps1.
    Writing bytes directly avoids text-mode translation (on Windows,
    write_text would turn LF into CRLF for every file, contradicting
    eol=lf); .bat/.ps1 content is converted to CRLF explicitly.
    """
    if target.suffix.lower() in (".bat", ".ps1"):
        data = content.replace("\r\n", "\n").replace("\n", "\r\n")
    else:
        # Normalize at the write boundary as well: parse_reply already
        # rejoins content with LF, but a CRLF-bearing content string
        # from any other path must not leak CRLF into an eol=lf file.
        data = content.replace("\r\n", "\n")
    target.write_bytes(data.encode("utf-8"))


def apply_reply(
    reply_text: str,
    root: Path,
    allow_tests: bool = False,
    test_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    check_runner: CheckRunner = run_check_commands,
    output_fn: OutputFn = print,
    manifest: Optional[Dict[str, Any]] = None,
    allow_new: Sequence[str] = (),
    force_stale: bool = False,
    allow_shrink: bool = False,
    allow_elision: bool = False,
) -> int:
    """Apply a parsed reply on a new git branch and run the checks.

    Returns 0 when the reply applied cleanly and all checks pass, 1
    otherwise. A rejected reply (incomplete, malformed, unsafe paths,
    or failing a WP2 guard) modifies no files and creates no branch.
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
    if manifest is None:
        output_fn(
            "Warning: no --manifest given; pack allowlist and "
            "stale-base checks are unavailable."
        )
    guard_problems = validate_apply_guards(
        parsed.blocks, root, manifest=manifest, allow_new=allow_new,
        force_stale=force_stale, allow_shrink=allow_shrink,
        allow_elision=allow_elision,
    )
    if guard_problems:
        output_fn(format_guard_reprompt(guard_problems))
        return 1

    branch = branch_name or f"agent-apply-{datetime.now():%Y%m%d-%H%M%S}"
    proc = _git(root, "checkout", "-b", branch)
    if proc.returncode != 0:
        output_fn(f"Error: could not create branch {branch}: {proc.stderr.strip()}")
        return 1

    changed: List[str] = []
    new_files: List[Tuple[str, int]] = []
    for rel_path, content in parsed.blocks:
        target = root / rel_path
        existed = target.is_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_content_file(target, content)
        changed.append(rel_path)
        if not existed:
            new_files.append((rel_path, len(content.splitlines())))
    output_fn(f"Applied {len(changed)} file(s) on branch {branch}:")
    for rel_path in changed:
        output_fn(f"  - {rel_path}")
    diff = _git(root, "diff", "--stat")
    if diff.returncode == 0 and diff.stdout.strip():
        output_fn("git diff --stat:")
        output_fn(diff.stdout.strip())
    if new_files:
        # git diff --stat covers tracked files only; name the new
        # (untracked) ones explicitly so they are not silently absent.
        output_fn("New files (untracked; not shown by git diff --stat):")
        for rel_path, line_count in new_files:
            output_fn(f"  - {rel_path} ({line_count} lines)")

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
    parts += ["## Rules", agents_md.strip(), ""]
    parts.append("## Files")
    for rel_path, content in file_contents:
        lang = "python" if rel_path.endswith(".py") else "text"
        fence = _fence_for_content(content)
        # Drop exactly one trailing newline: the join adds it back, so
        # a file ending in "\n\n" keeps both newlines in a round-trip
        # (rstrip("\n") would silently collapse them to one).
        body = content[:-1] if content.endswith("\n") else content
        parts += [f"### File: `{rel_path}`", f"{fence}{lang}", body,
                  fence, ""]
    if test_path:
        test_fence = _fence_for_content(test_output)
        parts += ["## Failing Tests", f"$ pytest {test_path} -q",
                  f"{test_fence}text", test_output, test_fence, ""]
    parts += [
        "## Reply Format (strict — follow exactly)",
        "Reply with ONLY file blocks, one per file you change, in this format:",
        "",
        "### File: `relative/path/from/repo/root.py`",
        "followed immediately by a fenced code block containing the COMPLETE "
        "new content of that file (full-file replacement — no diffs, no "
        "elision, no 'rest unchanged' placeholders).",
        "",
        "Use a fence of at least FOUR backticks for every file block "
        "(longer if the file itself contains a longer backtick run). "
        "Files in this repo contain ``` fences of their own; a 3-backtick "
        "outer fence would end the block at the first inner fence and "
        "silently truncate the file, so the longer fence is required, "
        "not cosmetic.",
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
    parser.add_argument("--rules", default=None,
                        help="Rules file to embed (default: AGENTS_WEB.md "
                             "if it exists, else AGENTS.md)")
    args = parser.parse_args(list(argv))

    root = _repo_root()
    file_contents: List[Tuple[str, str]] = []
    for rel in args.files:
        path = root / rel
        if not path.is_file():
            sys.stderr.write(f"Error: file not found in repo: {rel}\n")
            sys.exit(2)
        file_contents.append((rel, path.read_text(encoding="utf-8")))
    if args.rules:
        rules_path = Path(args.rules)
        if not rules_path.is_absolute():
            rules_path = root / rules_path
        if not rules_path.is_file():
            sys.stderr.write(f"Error: rules file not found: {args.rules}\n")
            sys.exit(2)
        agents_md = rules_path.read_text(encoding="utf-8")
    else:
        web_path = root / "AGENTS_WEB.md"
        agents_path = root / "AGENTS.md"
        if web_path.is_file():
            agents_md = web_path.read_text(encoding="utf-8")
        elif agents_path.is_file():
            agents_md = agents_path.read_text(encoding="utf-8")
        else:
            agents_md = "(no AGENTS_WEB.md or AGENTS.md found at repo root)"
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
        manifest_path = Path(f"{args.output}.manifest.json")
        manifest_path.write_text(
            json.dumps(build_manifest(file_contents), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote pack manifest to {manifest_path}")
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
    parser.add_argument("--manifest", default=None,
                        help="Pack manifest sidecar (bundle.md.manifest.json) "
                             "enabling the allowlist and stale-base guards")
    parser.add_argument("--allow-new", action="append", default=[],
                        help="Permit this target path even though it is not "
                             "in the manifest (repeatable)")
    parser.add_argument("--force-stale", action="store_true",
                        help="Apply even if a target's base drifted since pack")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Permit a file to shrink below 60% of its lines "
                             "or become empty")
    parser.add_argument("--allow-elision", action="store_true",
                        help="Skip the elision detector (for legitimate new "
                             "lines containing words like 'omitted')")
    args = parser.parse_args(list(argv))

    reply_path = Path(args.reply)
    if not reply_path.is_file():
        sys.stderr.write(f"Error: reply file not found: {reply_path}\n")
        sys.exit(2)
    manifest = None
    if args.manifest:
        manifest_file = Path(args.manifest)
        if not manifest_file.is_file():
            sys.stderr.write(f"Error: manifest file not found: {args.manifest}\n")
            sys.exit(2)
        try:
            manifest = load_manifest(manifest_file)
        except (ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"Error: could not load manifest: {exc}\n")
            sys.exit(2)
    code = apply_reply(
        reply_path.read_text(encoding="utf-8"),
        _repo_root(),
        allow_tests=args.allow_tests,
        test_path=args.test,
        branch_name=args.branch,
        manifest=manifest,
        allow_new=args.allow_new,
        force_stale=args.force_stale,
        allow_shrink=args.allow_shrink,
        allow_elision=args.allow_elision,
    )
    sys.exit(code)
