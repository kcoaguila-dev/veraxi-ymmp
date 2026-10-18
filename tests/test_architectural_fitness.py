"""Architectural Fitness and Privacy Invariant Tests.

These tests enforce Clean Architecture constraints and privacy invariants:
1. Zero hardcoded local user directories or current OS usernames across source, tests, and scripts.
2. Zero wildcard imports ('from x import *') in library code.
3. Maximum module size ceiling (900 lines) preventing monolithic/God modules.
4. Zero raw print() statements in core library modules (must use logging/veraxi_ymmp.logging).
5. Comprehensive unit verification of check_no_local_paths scanner logic.
"""

from __future__ import annotations

import ast
import getpass
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


from scripts.check_no_local_paths import (
    is_binary_file,
    scan_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_hardcoded_user_paths_or_os_username() -> None:
    """Ensure zero hardcoded user paths and zero occurrences of OS username in repo code."""
    current_user = getpass.getuser()

    directories_to_scan = [
        REPO_ROOT / "veraxi_ymmp",
        REPO_ROOT / "tests",
        REPO_ROOT / "scripts",
    ]

    all_targets: List[Path] = []
    for d in directories_to_scan:
        if d.is_dir():
            for p in d.rglob("*.py"):
                all_targets.append(p)

    # Root .py files
    for p in REPO_ROOT.glob("*.py"):
        all_targets.append(p)

    all_violations: List[str] = []
    for file_path in all_targets:
        violations = scan_file(file_path, current_user)
        all_violations.extend(violations)

    assert not all_violations, (
        f"Hardcoded user paths or username occurrences found ({len(all_violations)}):\n"
        + "\n".join(all_violations)
    )


def test_no_wildcard_imports_in_library() -> None:
    """Ensure zero wildcard imports ('from foo import *') in veraxi_ymmp/."""
    lib_dir = REPO_ROOT / "veraxi_ymmp"
    wildcards: List[Tuple[str, int]] = []

    for py_file in lib_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        wildcards.append((str(py_file.relative_to(REPO_ROOT)), node.lineno))

    assert not wildcards, f"Wildcard imports ('from module import *') found in library: {wildcards}"


def test_module_size_ceiling() -> None:
    """Ensure no module in veraxi_ymmp/ exceeds 900 lines of code (preventing God objects)."""
    lib_dir = REPO_ROOT / "veraxi_ymmp"
    max_allowed_lines = 900
    oversized_modules: List[Tuple[str, int]] = []

    for py_file in lib_dir.rglob("*.py"):
        lines = len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())
        if lines > max_allowed_lines:
            oversized_modules.append((str(py_file.relative_to(REPO_ROOT)), lines))

    assert not oversized_modules, (
        f"The following modules exceed the {max_allowed_lines} line ceiling: {oversized_modules}"
    )


def _is_main_guard(node: ast.AST) -> bool:
    """Return True if node is `if __name__ == '__main__':`."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if isinstance(test, ast.Compare):
        left = test.left
        for op, comparator in zip(test.ops, test.comparators):
            if isinstance(op, ast.Eq):
                if (
                    isinstance(left, ast.Name)
                    and left.id == "__name__"
                    and isinstance(comparator, ast.Constant)
                    and comparator.value == "__main__"
                ):
                    return True
                if (
                    isinstance(comparator, ast.Name)
                    and comparator.id == "__name__"
                    and isinstance(left, ast.Constant)
                    and left.value == "__main__"
                ):
                    return True
    return False


def _find_raw_prints_outside_main(tree: ast.AST) -> List[int]:
    """Find line numbers of print() calls outside `if __name__ == '__main__':` blocks."""
    prints: List[int] = []

    def visit(node: ast.AST, in_main: bool = False) -> None:
        if not in_main and _is_main_guard(node):
            in_main = True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print" and not in_main:
                prints.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, in_main)

    visit(tree)
    return prints


def test_no_raw_print_in_core_modules() -> None:
    """Ensure core library modules do not use raw print() statements outside __main__."""
    core_modules = [
        "compiler.py",
        "ir_builder.py",
        "ymmp_renderer.py",
        "psd_registry.py",
        "premiere_exporter.py",
        "moviepy_renderer.py",
        "voicevox.py",
        "broll.py",
        "thumbnail.py",
    ]

    violations: List[Tuple[str, List[int]]] = []
    for mod_name in core_modules:
        mod_path = REPO_ROOT / "veraxi_ymmp" / mod_name
        assert mod_path.is_file(), f"Expected core module {mod_name} not found at {mod_path}"
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        bad_prints = _find_raw_prints_outside_main(tree)
        if bad_prints:
            violations.append((mod_name, bad_prints))

    assert not violations, (
        f"Raw print() calls found in core library modules (use veraxi_ymmp.logging instead): {violations}"
    )


# --- Unit tests for check_no_local_paths scanner logic ---

def test_scanner_detects_forbidden_windows_path(tmp_path: Path) -> None:
    """Test scanner catches hardcoded non-allowed Windows user directory."""
    test_file = tmp_path / "win_test.txt"
    # Construct strings dynamically to avoid self-matching
    sep = "\\"
    bad_path = f"C:{sep}Users{sep}secretdeveloper{sep}project"
    test_file.write_text(f"PATH = '{bad_path}'\n", encoding="utf-8")

    violations = scan_file(test_file, current_user="otheruser")
    assert any("secretdeveloper" in v for v in violations)


def test_scanner_detects_forbidden_unix_paths(tmp_path: Path) -> None:
    """Test scanner catches hardcoded macOS and Linux user directories."""
    mac_file = tmp_path / "mac_test.txt"
    bad_mac = "/" + "Users" + "/" + "localdev/repo"
    mac_file.write_text(f"PATH = '{bad_mac}'\n", encoding="utf-8")
    violations_mac = scan_file(mac_file, current_user="otheruser")
    assert any("localdev" in v for v in violations_mac)

    linux_file = tmp_path / "linux_test.txt"
    bad_linux = "/" + "home" + "/" + "serveradmin/repo"
    linux_file.write_text(f"PATH = '{bad_linux}'\n", encoding="utf-8")
    violations_linux = scan_file(linux_file, current_user="otheruser")
    assert any("serveradmin" in v for v in violations_linux)


def test_scanner_allows_whitelisted_placeholders(tmp_path: Path) -> None:
    """Test scanner permits whitelisted placeholders (YourUser, Public, Default, etc.)."""
    test_file = tmp_path / "allowed_test.txt"
    sep = "\\"
    lines = [
        f"C:{sep}Users{sep}YourUser{sep}Documents",
        f"C:{sep}Users{sep}Public{sep}Desktop",
        f"C:{sep}Users{sep}Default{sep}AppData",
        "/" + "Users/YourUser/Projects",
        "/" + "home/runner/work",
    ]
    test_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    violations = scan_file(test_file, current_user="differentuser")
    assert not violations


def test_scanner_detects_secrets(tmp_path: Path) -> None:
    """Test scanner detects ghp_, github_pat_, sk-, AKIA secret patterns."""
    test_file = tmp_path / "secret_test.txt"
    # Dynamically compose tokens to prevent scanner false-positive on this test file
    tok_ghp = "gh" + "p_" + "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
    tok_pat = "github" + "_pat_" + "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
    tok_sk = "s" + "k-" + "proj0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
    tok_akia = "AK" + "IA" + "0123456789ABCDEF"  # pragma: allowlist secret

    test_file.write_text(
        f"a = '{tok_ghp}'\nb = '{tok_pat}'\nc = '{tok_sk}'\nd = '{tok_akia}'\n",
        encoding="utf-8",
    )

    violations = scan_file(test_file, current_user="differentuser")
    assert len(violations) == 4
    assert any("GitHub Personal Access Token" in v for v in violations)
    assert any("GitHub Fine-Grained PAT" in v for v in violations)
    assert any("OpenAI API Key" in v for v in violations)
    assert any("AWS Access Key ID" in v for v in violations)


def test_scanner_detects_os_username(tmp_path: Path) -> None:
    """Test scanner catches explicit occurrences of OS username."""
    test_file = tmp_path / "username_test.txt"
    test_file.write_text("Created by author: specialuser123 for internal use\n", encoding="utf-8")

    violations = scan_file(test_file, current_user="specialuser123")
    assert len(violations) == 1
    assert "specialuser123" in violations[0]


def test_scanner_skips_binary_files(tmp_path: Path) -> None:
    """Test scanner skips binary files with null bytes or binary extensions."""
    bin_file = tmp_path / "dummy.png"
    bin_secret = b"s" + b"k-secret1234567890"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bin_secret)
    assert is_binary_file(bin_file)

    violations = scan_file(bin_file, current_user="dummyuser")
    assert not violations


def test_mypy_strict_clean() -> None:
    """Ensure veraxi_ymmp has zero type errors under mypy."""
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "veraxi_ymmp"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"mypy checks failed with output:\n{res.stdout}\n{res.stderr}"
