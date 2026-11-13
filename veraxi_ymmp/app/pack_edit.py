"""Anchored edit mode for the web-chat fallback workflow (WP4).

``veraxi-ymmp apply-edit`` applies a web chat's SEARCH/REPLACE edit
blocks (produced from a ``pack --mode edit`` bundle) to the repo:

    ### Edit: `relative/path.py`
    <<<<<<< SEARCH
    (exact current text, copied from the bundle)
    =======
    (replacement text)
    >>>>>>> REPLACE
    ===END OF REPLY===

Exact-match blocks replace full-file replies for large files: the
model anchors on text it copied instead of producing line numbers
(unified diffs fail in confusing ways when the numbers drift), and
the reply cost scales with the change, not the file size.

Safety invariants (shared with :mod:`veraxi_ymmp.app.pack_apply`,
whose guards are reused rather than duplicated):

* Fail-closed uniqueness — every SEARCH text must occur exactly
  once in its (staged) target file; 0 or >1 matches rejects the
  whole reply with a non-zero exit code.
* All-or-nothing — every block is validated and staged in memory
  before any file is written or any branch is created, so a late
  failure leaves all files untouched.
* Encoding and line-ending fidelity — targets are decoded as UTF-8
  (Japanese text round-trips byte-exact); matching is done on
  LF-normalized text so a block copied from an LF bundle still
  anchors in a CRLF file, but the edit is spliced into the raw
  text, so line endings outside the edited span are preserved
  byte-for-byte — including in mixed-EOL files.
* The WP2 elision detector scans every REPLACE text, and the
  shared path-containment / tests-directory guards apply unchanged.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from veraxi_ymmp.app import pack_apply as pa

SEARCH_MARKER = "<<<<<<< SEARCH"
SEPARATOR = "======="
REPLACE_MARKER = ">>>>>>> REPLACE"

_EDIT_HEADER = re.compile(r"^### Edit:\s*`([^`]+)`\s*$")

OutputFn = Callable[[str], None]
CheckRunner = Callable[
    [List[str], Optional[str], Path], List[Tuple[str, str]]
]


@dataclass
class EditBlock:
    """One SEARCH/REPLACE block targeting ``path``."""

    path: str
    search: str
    replace: str


@dataclass
class ParsedEditReply:
    """Result of parsing an edit reply: blocks, or why it failed."""

    blocks: List[EditBlock] = field(default_factory=list)
    complete: bool = False
    problem: Optional[str] = None


def _split_lines(text: str) -> List[str]:
    """Split on LF only, tolerating CRLF line endings.

    ``str.splitlines()`` also splits on U+2028/U+2029 and other
    Unicode line boundaries, which would corrupt content containing
    those characters inside string literals when the lines are
    rejoined with "\\n".
    """
    return [
        line[:-1] if line.endswith("\r") else line
        for line in text.split("\n")
    ]


def parse_edit_reply(text: str) -> ParsedEditReply:
    """Parse an edit reply into blocks, failing closed on any defect.

    The reply must end with the END marker as its last non-empty
    line; anything unexpected outside a block, or a block missing
    its SEARCH/separator/REPLACE lines, makes the reply incomplete.
    """
    lines = _split_lines(text)
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    if not nonempty or lines[nonempty[-1]].strip() != pa.END_MARKER:
        return ParsedEditReply(
            problem=f"missing {pa.END_MARKER} at the end of the reply "
                    "(the reply may be truncated)"
        )
    end = nonempty[-1]
    blocks: List[EditBlock] = []
    i = 0
    while i < end:
        if not lines[i].strip():
            i += 1
            continue
        header = _EDIT_HEADER.match(lines[i].strip())
        if not header:
            return ParsedEditReply(
                problem="unexpected line outside an edit block: "
                        f"{lines[i].strip()[:60]!r}"
            )
        path = header.group(1)
        i += 1
        if i >= end or lines[i].strip() != SEARCH_MARKER:
            return ParsedEditReply(
                problem=f"{path}: expected '{SEARCH_MARKER}' after the "
                        "Edit header"
            )
        i += 1
        search_lines: List[str] = []
        while i < end and lines[i] != SEPARATOR:
            search_lines.append(lines[i])
            i += 1
        if i >= end:
            return ParsedEditReply(
                problem=f"{path}: missing '{SEPARATOR}' separator line"
            )
        i += 1
        replace_lines: List[str] = []
        while i < end and lines[i] != REPLACE_MARKER:
            replace_lines.append(lines[i])
            i += 1
        if i >= end:
            return ParsedEditReply(
                problem=f"{path}: missing '{REPLACE_MARKER}' terminator"
            )
        i += 1
        blocks.append(
            EditBlock(path, "\n".join(search_lines),
                      "\n".join(replace_lines))
        )
    if not blocks:
        return ParsedEditReply(problem="no edit blocks found in reply")
    return ParsedEditReply(blocks=blocks, complete=True)


def _normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _canonical_rel_path(rel_path: str, root: Path) -> str:
    """Canonical repo-relative identity for a target path.

    ``mod.py`` and ``./mod.py`` are the same file; staging keyed on
    the raw string would read the original twice and silently drop
    one block's edit when both staged copies are written back.
    """
    root_resolved = root.resolve()
    resolved = (root_resolved / rel_path).resolve()
    try:
        return resolved.relative_to(root_resolved).as_posix()
    except ValueError:
        return rel_path


def _normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """LF-normalize *text*, mapping each normalized offset to raw."""
    normalized: List[str] = []
    offsets: List[int] = []
    i = 0
    while i < len(text):
        if text[i] == "\r" and i + 1 < len(text) and (
            text[i + 1] == "\n"
        ):
            normalized.append("\n")
            offsets.append(i)
            i += 2
        else:
            normalized.append(text[i])
            offsets.append(i)
            i += 1
    offsets.append(len(text))
    return "".join(normalized), offsets


def _count_overlapping(text: str, needle: str) -> int:
    """Count possibly-overlapping occurrences (str.count does not)."""
    count = 0
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            return count
        count += 1
        start = idx + 1


def _match_span(
    current: str, search_lf: str
) -> Tuple[int, Optional[Tuple[int, int]]]:
    """Count SEARCH matches; locate the raw span of a unique one.

    Matching runs on LF-normalized text so a block copied from an
    LF bundle anchors in a CRLF file; the returned span indexes the
    raw text, so everything outside the span keeps its original
    bytes and line endings.
    """
    normalized, offsets = _normalize_with_map(current)
    count = _count_overlapping(normalized, search_lf)
    if count != 1:
        return count, None
    start = normalized.find(search_lf)
    end = start + len(search_lf)
    return count, (offsets[start], offsets[end])


def _region_eol(text: str, start: int, end: int) -> str:
    """Line ending to give replacement text spliced at text[start:end]."""
    span = text[start:end]
    if "\r\n" in span:
        return "\r\n"
    if "\n" in span:
        return "\n"
    if text[end : end + 2] == "\r\n":
        return "\r\n"
    if text[end : end + 1] == "\n":
        return "\n"
    newline = text.find("\n")
    if newline > 0 and text[newline - 1] == "\r":
        return "\r\n"
    return "\n"


def _stage_edits(
    blocks: List[EditBlock], root: Path
) -> Tuple[Dict[str, str], List[str]]:
    """Validate and stage every block in memory; write nothing.

    Returns ``({canonical_path: new_raw_text}, problems)``. Blocks
    for the same file apply sequentially to the staged text, so a
    later block anchors on the result of the earlier ones.
    """
    staged: Dict[str, str] = {}
    originals: Dict[str, str] = {}
    problems: List[str] = []
    for block in blocks:
        canonical = _canonical_rel_path(block.path, root)
        if canonical not in staged:
            target = root / canonical
            if not target.is_file():
                problems.append(
                    f"{block.path}: target file does not exist"
                )
                continue
            try:
                original = target.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                problems.append(
                    f"{block.path}: target file is not valid UTF-8"
                )
                continue
            originals[canonical] = _normalize_lf(original)
            staged[canonical] = original
        current = staged[canonical]
        search = _normalize_lf(block.search)
        if not search:
            problems.append(f"{block.path}: empty SEARCH block")
            continue
        count, span = _match_span(current, search)
        if count == 0:
            problems.append(
                f"{block.path}: SEARCH text not found (0 matches); "
                "copy it exactly from the current file"
            )
            continue
        if count > 1 or span is None:
            problems.append(
                f"{block.path}: SEARCH text matches {count} places; "
                "add surrounding context lines to make it unique"
            )
            continue
        replace = _normalize_lf(block.replace)
        problems.extend(
            pa._elision_problems(block.path, replace,
                                 originals[canonical])
        )
        start, end = span
        if _region_eol(current, start, end) == "\r\n":
            replace = replace.replace("\n", "\r\n")
        staged[canonical] = current[:start] + replace + current[end:]
    return staged, problems


def format_edit_reprompt(problems: List[str]) -> str:
    """Re-prompt block for edit replies rejected before any write."""
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) "
        "================",
        "Your edit reply was NOT applied because:",
    ]
    for problem in problems:
        lines.append(f"  - [EDIT] {problem}")
    lines.append(
        "Please resend the edit blocks with SEARCH text copied "
        "exactly from the current file contents — each SEARCH must "
        f"match exactly once — ending with a line containing only "
        f"{pa.END_MARKER}."
    )
    lines.append("=" * 74)
    return "\n".join(lines)


def apply_edit_reply(
    reply_text: str,
    root: Path,
    allow_tests: bool = False,
    test_path: Optional[str] = None,
    branch_name: Optional[str] = None,
    check_runner: CheckRunner = pa.run_check_commands,
    output_fn: OutputFn = print,
) -> int:
    """Apply an edit reply on a new branch and run the checks.

    Returns 0 on success, 1 otherwise. A rejected reply (malformed,
    unsafe path, failed anchor, elision hit) modifies no files and
    creates no branch.
    """
    parsed = parse_edit_reply(reply_text)
    if not parsed.complete or not parsed.blocks:
        output_fn(
            f"Error: edit reply rejected — {parsed.problem}. "
            "No files modified."
        )
        return 1
    path_errors = pa.validate_target_paths(
        [(block.path, block.replace) for block in parsed.blocks],
        root, allow_tests,
    )
    if path_errors:
        for error in path_errors:
            output_fn(
                f"Error: edit reply rejected — {error}. "
                "No files modified."
            )
        return 1
    staged, problems = _stage_edits(parsed.blocks, root)
    if problems:
        output_fn(format_edit_reprompt(problems))
        return 1

    branch = branch_name or f"agent-edit-{datetime.now():%Y%m%d-%H%M%S}"
    proc = pa._git(root, "checkout", "-b", branch)
    if proc.returncode != 0:
        output_fn(
            f"Error: could not create branch {branch}: "
            f"{proc.stderr.strip()}"
        )
        return 1
    for rel_path, new_text in staged.items():
        (root / rel_path).write_bytes(new_text.encode("utf-8"))
    output_fn(
        f"Applied {len(parsed.blocks)} edit block(s) to "
        f"{len(staged)} file(s) on branch {branch}:"
    )
    for rel_path in staged:
        output_fn(f"  - {rel_path}")
    diff = pa._git(root, "diff", "--stat")
    if diff.returncode == 0 and diff.stdout.strip():
        output_fn("git diff --stat:")
        output_fn(diff.stdout.strip())
    failures = check_runner(list(staged), test_path, root)
    if failures:
        output_fn(pa.format_check_reprompt(branch, failures))
        return 1
    output_fn("All checks passed (ruff, mypy, targeted pytest).")
    return 0


def cmd_apply_edit(argv: Sequence[str]) -> None:
    """Handle 'veraxi-ymmp apply-edit'."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp apply-edit",
        description="Apply a web chat's SEARCH/REPLACE edit blocks.",
    )
    parser.add_argument("reply", help="Path to the saved edit reply (.md)")
    parser.add_argument("--allow-tests", action="store_true",
                        help="Allow the edits to modify files under tests/")
    parser.add_argument("--test", default=None,
                        help="Targeted pytest file to run after applying")
    parser.add_argument("--branch", default=None,
                        help="Branch name to create "
                             "(default: agent-edit-<timestamp>)")
    args = parser.parse_args(list(argv))

    reply_path = Path(args.reply)
    if not reply_path.is_file():
        sys.stderr.write(f"Error: reply file not found: {args.reply}\n")
        sys.exit(2)
    code = apply_edit_reply(
        reply_path.read_text(encoding="utf-8"),
        pa._repo_root(),
        allow_tests=args.allow_tests,
        test_path=args.test,
        branch_name=args.branch,
    )
    sys.exit(code)
