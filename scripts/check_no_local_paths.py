#!/usr/bin/env python3
"""Check for hardcoded local user paths, current OS username, and secrets in repository files.

Ensures that:
1. No hardcoded Windows/macOS/Linux user directories (C:\\Users\\<user>, /Users/<user>, /home/<user>)
   are committed, unless the username is an allowed placeholder (e.g. YourUser, Public, Default).
2. The current OS username (getpass.getuser()) never appears anywhere in the codebase.
3. Common secret/token patterns (ghp_, github_pat_, sk-, AKIA) are blocked.

Exit status:
0: All checks passed.
1: Violations found.
"""

from __future__ import annotations

import argparse
import getpass
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple

# Allowed placeholder usernames in documentation or template configs
ALLOWED_USERNAMES: Set[str] = {
    "YourUser",
    "Public",
    "Default",
    "All Users",
    "...",
    "runner",
    "runneradmin",
}

# Generic service accounts that shouldn't trigger standalone word matching in CI
GENERIC_CI_USERS: Set[str] = {
    "runner",
    "runneradmin",
    "root",
    "none",
    "administrator",
    "system",
}

# Directories to skip entirely
IGNORED_DIRS: Set[str] = {
    ".git",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".vscode",
    "build",
    "dist",
}

# Binary and non-scannable file extensions
BINARY_EXTENSIONS: Set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".psd",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".pdf",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyc",
    ".pyd",
}

# Compiled regexes for user directory detection
WIN_USER_PATH_PATTERN = re.compile(
    r"[A-Za-z]:(?:\\\\|/|\\)Users(?:\\\\|/|\\)([^\\\\/\s\"\'<>`]+)",
    re.IGNORECASE,
)
MAC_USER_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"\'`=:(])/Users/([^/\\\s\"\'<>`]+)",
    re.IGNORECASE,
)
LINUX_USER_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"\'`=:(])/home/([^/\\\s\"\'<>`]+)",
    re.IGNORECASE,
)

# Common secret/token patterns
SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("GitHub Personal Access Token", re.compile(r"\bghp_[A-Za-z0-9_]{10,}\b")),
    ("GitHub Fine-Grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{10,}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


def is_binary_file(filepath: Path) -> bool:
    """Return True if the file has a binary extension or contains null bytes."""
    if filepath.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
    except OSError:
        return True
    return False


def get_current_os_username() -> str:
    """Retrieve the current OS login username safely."""
    try:
        user = getpass.getuser()
        return user.strip()
    except Exception:
        return ""


def get_staged_files() -> List[str]:
    """Retrieve list of staged files in git."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def get_all_tracked_files() -> List[str]:
    """Retrieve all tracked files in git."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def scan_file(filepath: Path, current_user: str) -> List[str]:
    """Scan a single file for path, username, and secret violations.

    Returns a list of diagnostic violation messages.
    """
    violations: List[str] = []

    # Skip files inside ignored directories or the script itself
    parts = filepath.parts
    for part in parts:
        if part in IGNORED_DIRS or part.endswith(".egg-info"):
            return []
    if filepath.name == "check_no_local_paths.py":
        return []

    if not filepath.is_file():
        return []

    if is_binary_file(filepath):
        return []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"[ERROR] Cannot read {filepath}: {e}"]

    # Setup username match pattern if current_user is valid and not generic
    user_pattern: re.Pattern[str] | None = None
    if (
        current_user
        and len(current_user) >= 2
        and current_user.lower() not in GENERIC_CI_USERS
        and current_user not in ALLOWED_USERNAMES
    ):
        user_pattern = re.compile(rf"\b{re.escape(current_user)}\b", re.IGNORECASE)

    for line_idx, line in enumerate(content.splitlines(), start=1):
        # 1. Check Windows user path
        for match in WIN_USER_PATH_PATTERN.finditer(line):
            uname = match.group(1).strip()
            if uname not in ALLOWED_USERNAMES:
                violations.append(
                    f"[LOCAL_PATH] {filepath}:{line_idx}: Hardcoded Windows user path found: "
                    f"'{match.group(0)}' (user '{uname}' not in allowlist)"
                )

        # 2. Check macOS user path
        for match in MAC_USER_PATH_PATTERN.finditer(line):
            uname = match.group(1).strip()
            if uname not in ALLOWED_USERNAMES:
                violations.append(
                    f"[LOCAL_PATH] {filepath}:{line_idx}: Hardcoded macOS user path found: "
                    f"'{match.group(0)}' (user '{uname}' not in allowlist)"
                )

        # 3. Check Linux user path
        for match in LINUX_USER_PATH_PATTERN.finditer(line):
            uname = match.group(1).strip()
            if uname not in ALLOWED_USERNAMES:
                violations.append(
                    f"[LOCAL_PATH] {filepath}:{line_idx}: Hardcoded Linux user path found: "
                    f"'{match.group(0)}' (user '{uname}' not in allowlist)"
                )

        # 4. Check Current OS username
        if user_pattern:
            for match in user_pattern.finditer(line):
                violations.append(
                    f"[OS_USERNAME] {filepath}:{line_idx}: Current OS username '{current_user}' detected: "
                    f"'{line.strip()}'"
                )

        # 5. Check Secrets
        for secret_name, secret_regex in SECRET_PATTERNS:
            for match in secret_regex.finditer(line):
                masked = match.group(0)[:4] + "..." + match.group(0)[-3:]
                violations.append(
                    f"[SECRET_TOKEN] {filepath}:{line_idx}: {secret_name} pattern detected: '{masked}'"
                )

    return violations


def run_checks(targets: Iterable[str | Path]) -> int:
    """Run check against given file paths. Returns exit code (0 or 1)."""
    current_user = get_current_os_username()
    all_violations: List[str] = []
    scanned_count = 0

    for target in targets:
        path = Path(target)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    v = scan_file(child, current_user)
                    all_violations.extend(v)
                    scanned_count += 1
        elif path.is_file():
            v = scan_file(path, current_user)
            all_violations.extend(v)
            scanned_count += 1

    if all_violations:
        print("=" * 70, file=sys.stderr)
        print("SECURITY & PRIVACY VIOLATIONS DETECTED!", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for v in all_violations:
            print(f"  ❌ {v}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(f"Total violations found: {len(all_violations)}", file=sys.stderr)
        print("Commit rejected. Please eliminate hardcoded paths, local usernames, and secrets.", file=sys.stderr)
        return 1

    print(f"✅ check_no_local_paths: {scanned_count} files checked cleanly. No leaks found.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify no local paths, OS usernames, or secrets exist in repository files."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all tracked repository files instead of only staged files.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to check (passed by git pre-commit hook).",
    )
    args = parser.parse_args(argv)

    if args.files:
        targets = args.files
    elif args.all:
        targets = get_all_tracked_files()
    else:
        # Default: staged files
        targets = get_staged_files()
        if not targets:
            # Fallback if no staged files found
            targets = get_all_tracked_files()

    return run_checks(targets)


if __name__ == "__main__":
    sys.exit(main())
