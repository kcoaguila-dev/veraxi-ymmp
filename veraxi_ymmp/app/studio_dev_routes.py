"""Tier 3 Studio routes for the web-chat *developer* fallback (WP1-WP8).

Exposes the code-editing fallback in the Studio GUI as a separate Dev view,
reusing the exact CLI library functions so the fail-closed guards cannot
drift between surfaces:

- ``POST /api/dev/session-start`` — ``session_start.build_session_start``
  (rules + git state + TODOs paste for a fresh web chat).
- ``POST /api/dev/pack`` — ``pack_apply.build_pack_bundle`` with the same
  rules selection, budget check, and manifest sidecar as ``veraxi-ymmp
  pack``; the manifest is kept server-side under a ``pack_id`` so the
  matching apply can run the stale-base guard.
- ``POST /api/dev/apply`` + ``POST /api/dev/apply/status`` —
  ``pack_apply.apply_reply`` / ``pack_edit.apply_edit_reply`` run as a
  single-flight background job (apply runs ruff/mypy/pytest, so the GUI
  polls). The GUI deliberately exposes *fewer* escape hatches than the
  CLI: no force-stale / allow-shrink / allow-elision / allow-new
  overrides, so a pasted reply either passes every guard or writes
  nothing and creates no branch.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from veraxi_ymmp.app import pack_apply as pa
from veraxi_ymmp.app import pack_edit as pe
from veraxi_ymmp.app.session_start import build_session_start


def _dev_root() -> Path:
    """Repo the dev fallback operates on (the one this backend runs from)."""
    return pa._repo_root()


_pack_manifests: Dict[str, Dict[str, Any]] = {}
_apply_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def handle_dev_session_start() -> Tuple[int, Dict[str, Any]]:
    """Return the session-start paste (rules, git state, TODOs, cheatsheet)."""
    try:
        text = build_session_start(_dev_root())
    except Exception as exc:  # git missing / not a repo: surface, don't 500
        return 400, {"success": False, "error": f"session-start failed: {exc}"}
    return 200, {"success": True, "text": text}


def handle_dev_pack(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Build a pack bundle + manifest, mirroring ``veraxi-ymmp pack``."""
    task = body.get("task")
    if not isinstance(task, str) or not task.strip():
        return 400, {"success": False, "error": "task is required"}
    files = body.get("files")
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(f, str) and f.strip() for f in files)
    ):
        return 400, {"success": False, "error": "files must be a non-empty list"}
    mode = body.get("mode", "full")
    if mode not in ("full", "edit"):
        return 400, {"success": False, "error": "mode must be 'full' or 'edit'"}
    test_path = body.get("test") or None
    if test_path is not None and not isinstance(test_path, str):
        return 400, {"success": False, "error": "test must be a string path"}

    root = _dev_root()
    file_contents: List[Tuple[str, str]] = []
    for rel in files:
        resolved = (root / rel).resolve()
        if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
            return 400, {"success": False, "error": f"file not found in repo: {rel}"}
        file_contents.append((rel, resolved.read_text(encoding="utf-8")))

    web_path = root / "AGENTS_WEB.md"
    agents_path = root / "AGENTS.md"
    if web_path.is_file():
        agents_md = web_path.read_text(encoding="utf-8")
    elif agents_path.is_file():
        agents_md = agents_path.read_text(encoding="utf-8")
    else:
        agents_md = "(no AGENTS_WEB.md or AGENTS.md found at repo root)"
    # cmd_pack appends the project pack rules in every default-rules case.
    extra_rules = pe.build_project_pack_rules(files)
    if extra_rules:
        agents_md = f"{agents_md.rstrip()}\n\n{extra_rules}"

    test_output = pa._run_failing_test(test_path, root) if test_path else ""
    bundle = pa.build_pack_bundle(
        task, file_contents, agents_md,
        test_path=test_path, test_output=test_output, mode=mode,
    )
    if len(bundle) > pa.DEFAULT_BUDGET:
        return 400, {
            "success": False,
            "error": (
                f"pack bundle is {len(bundle)} characters, over the "
                f"{pa.DEFAULT_BUDGET}-character budget. Split the task or "
                "name fewer files; refusing to truncate silently."
            ),
        }
    pack_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _pack_manifests[pack_id] = pa.build_manifest(file_contents)
    return 200, {
        "success": True,
        "pack_id": pack_id,
        "bundle": bundle,
        "chars": len(bundle),
        "files": [rel for rel, _ in file_contents],
        "mode": mode,
    }


def handle_dev_apply_start(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Start a single-flight apply job for a pasted web-chat reply."""
    reply = body.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return 400, {"success": False, "error": "reply is required"}
    mode = body.get("mode", "full")
    if mode not in ("full", "edit"):
        return 400, {"success": False, "error": "mode must be 'full' or 'edit'"}
    pack_id = body.get("pack_id") or None
    allow_tests = bool(body.get("allow_tests", False))
    test_path = body.get("test") or None
    if test_path is not None and not isinstance(test_path, str):
        return 400, {"success": False, "error": "test must be a string path"}

    with _jobs_lock:
        if any(j["status"] == "running" for j in _apply_jobs.values()):
            return 409, {
                "success": False,
                "error": "an apply job is already running; wait for it to finish",
            }
        job_id = uuid.uuid4().hex[:12]
        _apply_jobs[job_id] = {"status": "running", "exit_code": None, "output": ""}
        manifest: Optional[Dict[str, Any]] = (
            _pack_manifests.get(pack_id) if pack_id else None
        )

    root = _dev_root()

    def _run() -> None:
        lines: List[str] = []
        try:
            if mode == "edit":
                rc = pe.apply_edit_reply(
                    reply, root,
                    allow_tests=allow_tests, test_path=test_path,
                    output_fn=lines.append,
                )
            else:
                rc = pa.apply_reply(
                    reply, root,
                    allow_tests=allow_tests, test_path=test_path,
                    output_fn=lines.append, manifest=manifest,
                )
        except Exception as exc:  # apply must fail closed, never crash the API
            lines.append(f"Error: apply failed unexpectedly: {exc}")
            rc = 1
        with _jobs_lock:
            _apply_jobs[job_id] = {
                "status": "done",
                "exit_code": rc,
                "output": "\n".join(lines),
            }

    threading.Thread(target=_run, daemon=True).start()
    return 200, {"success": True, "job_id": job_id}


def handle_dev_apply_status(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Poll an apply job started by :func:`handle_dev_apply_start`."""
    job_id = body.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return 400, {"success": False, "error": "job_id is required"}
    with _jobs_lock:
        job = _apply_jobs.get(job_id)
        if job is None:
            return 404, {"success": False, "error": f"unknown job_id: {job_id}"}
        return 200, {"success": True, **job}
