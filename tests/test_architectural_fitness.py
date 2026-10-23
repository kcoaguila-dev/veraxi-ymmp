"""Architectural Fitness and Privacy Invariant Tests.

These tests enforce Clean Architecture constraints and privacy invariants:
1. Zero hardcoded local user directories or current OS usernames across source, tests, and scripts.
2. Zero wildcard imports ('from x import *') in library code.
3. Maximum module size ceiling (900 lines) preventing monolithic/God modules.
4. Zero raw print() statements in core library modules (must use logging/veraxi_ymmp.logging).
5. Comprehensive unit verification of check_no_local_paths scanner logic.
6. Zero cross-adapter imports among renderer/exporter adapters.
7. Pure domain layer modules never import infrastructure or adapter modules.
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
            for ext in ("*.py", "*.jsx"):
                for p in d.rglob(ext):
                    all_targets.append(p)

    # Root .py and .jsx files
    for ext in ("*.py", "*.jsx"):
        for p in REPO_ROOT.glob(ext):
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
    import pytest
    pytest.importorskip("mypy")
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "veraxi_ymmp"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert res.returncode == 0, f"mypy checks failed with output:\n{res.stdout}\n{res.stderr}"


def _extract_imported_module_names(tree: ast.AST) -> List[Tuple[str, int]]:
    """Extract (module_reference, lineno) for all imports in an AST."""
    imports: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.module, node.lineno))
                for alias in node.names:
                    imports.append((f"{node.module}.{alias.name}", node.lineno))
            else:
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
    return imports


def _matches_module(import_ref: str, module_name: str) -> bool:
    """Return True if import_ref matches module_name as full name or member."""
    if import_ref == module_name:
        return True
    if import_ref.startswith(f"{module_name}."):
        return True
    if import_ref.endswith(f".{module_name}"):
        return True
    if f".{module_name}." in import_ref:
        return True
    return False


def test_no_cross_adapter_imports() -> None:
    """Ensure renderer/exporter adapters never import from peer renderer/exporter adapters."""
    adapter_files = [
        "ymmp_renderer.py",
        "premiere_exporter.py",
        "moviepy_renderer.py",
        "ae_renderer.py",
        "srt_generator.py",
    ]
    lib_dir = REPO_ROOT / "veraxi_ymmp"
    violations: List[str] = []

    for file_name in adapter_files:
        file_path = lib_dir / file_name
        assert file_path.is_file(), f"Adapter file not found: {file_path}"
        forbidden_mods = [f.replace(".py", "") for f in adapter_files if f != file_name]

        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imported = _extract_imported_module_names(tree)

        for mod_ref, lineno in imported:
            for forbidden in forbidden_mods:
                if _matches_module(mod_ref, forbidden):
                    violations.append(
                        f"{file_name}:{lineno} illegal cross-adapter import '{forbidden}' (ref: '{mod_ref}')"
                    )

    assert not violations, (
        f"Cross-adapter imports found ({len(violations)}):\n" + "\n".join(violations)
    )


def test_domain_layer_purity() -> None:
    """Ensure pure domain modules never import infrastructure or adapter modules."""
    domain_files = [
        "ir.py",
        "script.py",
        "constants.py",
    ]
    forbidden_modules = [
        "voicevox",
        "ymmp_renderer",
        "premiere_exporter",
        "moviepy_renderer",
        "ae_renderer",
        "thumbnail",
        "broll",
        "cli",
        "cli_youtube",
        "mcp_server",
    ]
    lib_dir = REPO_ROOT / "veraxi_ymmp"
    violations: List[str] = []

    for file_name in domain_files:
        file_path = lib_dir / file_name
        assert file_path.is_file(), f"Domain file not found: {file_path}"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imported = _extract_imported_module_names(tree)

        for mod_ref, lineno in imported:
            for forbidden in forbidden_modules:
                if _matches_module(mod_ref, forbidden):
                    violations.append(
                        f"{file_name}:{lineno} pure domain module illegally imports infrastructure/adapter '{forbidden}' (ref: '{mod_ref}')"
                    )

    assert not violations, (
        f"Domain layer purity violations found ({len(violations)}):\n" + "\n".join(violations)
    )


def test_ports_layer_purity() -> None:
    """Ensure veraxi_ymmp/ports.py only imports domain modules or standard library and never concrete adapters."""
    ports_file = REPO_ROOT / "veraxi_ymmp" / "ports.py"
    assert ports_file.is_file(), f"Ports file not found: {ports_file}"

    tree = ast.parse(ports_file.read_text(encoding="utf-8"), filename=str(ports_file))
    allowed_roots = {
        "__future__",
        "typing",
        "dataclasses",
        "pathlib",
        "ir",
        "script",
        "constants",
        "director",
        "veraxi_ymmp.ir",
        "veraxi_ymmp.script",
        "veraxi_ymmp.constants",
        "veraxi_ymmp.director",
    }
    forbidden_adapters = {
        "voicevox",
        "ymmp_renderer",
        "premiere_exporter",
        "moviepy_renderer",
        "ae_renderer",
        "srt_generator",
        "thumbnail",
        "broll",
        "cli",
        "cli_youtube",
        "mcp_server",
        "pipeline",
    }

    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod not in allowed_roots or any(
                    _matches_module(alias.name, f) for f in forbidden_adapters
                ):
                    violations.append(f"ports.py:{node.lineno} disallowed import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(_matches_module(mod, f) for f in forbidden_adapters):
                violations.append(f"ports.py:{node.lineno} forbidden adapter import '{mod}'")
            elif mod and mod not in allowed_roots:
                violations.append(f"ports.py:{node.lineno} disallowed import from '{mod}'")

    assert not violations, (
        f"Ports layer purity violations found ({len(violations)}):\n" + "\n".join(violations)
    )


def test_no_loose_scripts_in_repo_root() -> None:
    """Ensure repository root contains zero loose .py or .jsx scripts."""
    loose_py = [p.name for p in REPO_ROOT.glob("*.py")]
    loose_jsx = [p.name for p in REPO_ROOT.glob("*.jsx")]
    loose = sorted(loose_py + loose_jsx)
    assert not loose, f"Loose scripts found in repository root (move to veraxi_ymmp/cli.py or scripts/): {loose}"
